import torch
import torch.nn as nn
from memory import DKVMN
import numpy as np
import utils as utils

class MODEL(nn.Module):

    def __init__(self, n_question, batch_size, q_embed_dim, qa_embed_dim,
                 memory_size, memory_key_state_dim, memory_value_state_dim, final_fc_dim, student_num=None):
        super(MODEL, self).__init__()
        self.n_question = n_question
        self.batch_size = batch_size
        self.q_embed_dim = q_embed_dim
        self.qa_embed_dim = qa_embed_dim
        self.memory_size = memory_size
        self.memory_key_state_dim = memory_key_state_dim
        self.memory_value_state_dim = memory_value_state_dim
        self.final_fc_dim = final_fc_dim
        self.student_num = student_num
        print(self.n_question, self.batch_size, self.memory_size, self.final_fc_dim, self.student_num, self.q_embed_dim)

        self.input_embed_linear = nn.Linear(self.q_embed_dim, self.final_fc_dim, bias=True)
        self.read_embed_linear = nn.Linear(self.memory_value_state_dim + self.final_fc_dim, self.final_fc_dim, bias=True)
        self.predict_linear = nn.Linear(self.final_fc_dim, 1, bias=True)
        self.predict_linear_theta = nn.Linear(self.final_fc_dim, 1, bias=True)
        self.predict_linear_beta = nn.Linear(self.final_fc_dim, 1, bias=True)
        self.init_memory_key = nn.Parameter(torch.randn(self.memory_size, self.memory_key_state_dim))
        nn.init.kaiming_normal_(self.init_memory_key)
        self.init_memory_value = nn.Parameter(torch.randn(self.memory_size, self.memory_value_state_dim))
        nn.init.kaiming_normal_(self.init_memory_value)

        self.mem = DKVMN(memory_size=self.memory_size,
                   memory_key_state_dim=self.memory_key_state_dim,
                   memory_value_state_dim=self.memory_value_state_dim, init_memory_key=self.init_memory_key)

        memory_value = nn.Parameter(torch.cat([self.init_memory_value.unsqueeze(0) for _ in range(batch_size)], 0).data)
        self.mem.init_value_memory(memory_value)

        self.q_embed = nn.Embedding(self.n_question + 1, self.q_embed_dim, padding_idx=0)
        self.qa_embed = nn.Embedding(2 * self.n_question + 1, self.qa_embed_dim, padding_idx=0)

    def init_params(self):
        nn.init.kaiming_normal_(self.predict_linear.weight)
        nn.init.kaiming_normal_(self.predict_linear_theta.weight)
        nn.init.kaiming_normal_(self.predict_linear_beta.weight)
        nn.init.kaiming_normal_(self.read_embed_linear.weight)
        nn.init.constant_(self.read_embed_linear.bias, 0)
        nn.init.constant_(self.predict_linear_theta.bias, 0)
        nn.init.constant_(self.predict_linear.bias, 0)
        nn.init.constant_(self.predict_linear_beta.bias, 0)
        # nn.init.constant(self.input_embed_linear.bias, 0)
        # nn.init.normal(self.input_embed_linear.weight, std=0.02)

    def init_embeddings(self):

        nn.init.kaiming_normal_(self.q_embed.weight)
        nn.init.kaiming_normal_(self.qa_embed.weight)

    def forward(self, q_data, qa_data, target, student_id=None):
        batch_size = q_data.shape[0]
        seqlen = q_data.shape[1]
        q_embed_data = self.q_embed(q_data)
        qa_embed_data = self.qa_embed(qa_data)

        memory_value = nn.Parameter(torch.cat([self.init_memory_value.unsqueeze(0) for _ in range(batch_size)], 0).data)
        self.mem.init_value_memory(memory_value)
        slice_q_data = torch.chunk(q_data, seqlen, 1)
        slice_q_embed_data = torch.chunk(q_embed_data, seqlen, 1)
        slice_qa_embed_data = torch.chunk(qa_embed_data, seqlen, 1)

        value_read_content_l = []
        input_embed_l = []
        predict_logs = []
        for i in range(seqlen):
            ## Attention
            q = slice_q_embed_data[i].squeeze(1)
            correlation_weight = self.mem.attention(q)
            if_memory_write = slice_q_data[i].squeeze(1).ge(1)
            if_memory_write = utils.varible(torch.FloatTensor(if_memory_write.data.tolist()), 1)
            ## Read Process
            read_content = self.mem.read(correlation_weight)
            value_read_content_l.append(read_content)
            input_embed_l.append(q)

            ## Write Process
            qa = slice_qa_embed_data[i].squeeze(1)
            new_memory_value = self.mem.write(correlation_weight, qa, if_memory_write)

            # read_content_embed = torch.tanh(self.read_embed_linear(torch.cat([read_content, q], 1)))
            # pred = self.predict_linear(read_content_embed)
            # predict_logs.append(pred)

        all_read_value_content = torch.cat([value_read_content_l[i].unsqueeze(1) for i in range(seqlen)], 1)
        input_embed_content = torch.cat([input_embed_l[i].unsqueeze(1) for i in range(seqlen)], 1)
        # input_embed_content = input_embed_content.view(batch_size * seqlen, -1)
        # input_embed_content = torch.tanh(self.input_embed_linear(input_embed_content))
        # input_embed_content = input_embed_content.view(batch_size, seqlen, -1)
        predict_input = torch.cat([all_read_value_content, input_embed_content], 2)
        read_content_embed = torch.tanh(self.read_embed_linear(predict_input.view(batch_size*seqlen, -1)))

        
        input_embed_content = torch.reshape(input_embed_content, (-1, 50))
        # print(read_content_embed.size())
        # print(input_embed_content.size())
        # print('------------------------')
        student_ability = torch.tanh(self.predict_linear_theta(read_content_embed))
        question_difficulty = torch.tanh(self.predict_linear_beta(input_embed_content))
        pred_ = 3.0 * student_ability - question_difficulty

        pred = self.predict_linear(read_content_embed)
        # predicts = torch.cat([predict_logs[i] for i in range(seqlen)], 1)
        target_1d = target                 # [batch_size * seq_len, 1]
        mask = target_1d.ge(0)               # [batch_size * seq_len, 1]
        # pred_1d = predicts.view(-1, 1)           # [batch_size * seq_len, 1]
        pred_1d = pred_.view(-1, 1)           # [batch_size * seq_len, 1]
        memory = self.mem.memory_value
        new_memory = []
        for i in range(len(memory)):
            new_memory.append(memory[i][0])
        new_memory = torch.stack(new_memory)
        new_memory = new_memory.view(-1, 1)
        new_memory = torch.masked_select(new_memory, mask)



        filtered_pred = torch.masked_select(pred_1d, mask)
        
        q_data = q_data.view(-1, 1)
        q_test = torch.masked_select(q_data, mask)
        filtered_target = torch.masked_select(target_1d, mask)
        filtered_student_ability = torch.masked_select(student_ability, mask)
        filtered_question_difficulty = torch.masked_select(question_difficulty, mask)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(filtered_pred, filtered_target)

        return q_test, loss, torch.sigmoid(filtered_pred), filtered_target, filtered_student_ability, filtered_question_difficulty, memory, mask
    def forward_test(self, q_data, qa_data, target, student_id=None):
        batch_size = q_data.shape[0]
        seqlen = q_data.shape[1]
        q_embed_data = self.q_embed(q_data)
        qa_embed_data = self.qa_embed(qa_data)

        memory_value = nn.Parameter(torch.cat([self.init_memory_value.unsqueeze(0) for _ in range(batch_size)], 0).data)
        self.mem.init_value_memory(memory_value)
        slice_q_data = torch.chunk(q_data, seqlen, 1)
        slice_q_embed_data = torch.chunk(q_embed_data, seqlen, 1)
        slice_qa_embed_data = torch.chunk(qa_embed_data, seqlen, 1)

        value_read_content_l = []
        input_embed_l = []
        predict_logs = []
        for i in range(seqlen):
            ## Attention
            q = slice_q_embed_data[i].squeeze(1)
            correlation_weight = self.mem.attention(q)
            if_memory_write = slice_q_data[i].squeeze(1).ge(1)
            if_memory_write = utils.varible(torch.FloatTensor(if_memory_write.data.tolist()), 1)
            ## Read Process
            read_content = self.mem.read(correlation_weight)
            value_read_content_l.append(read_content)
            input_embed_l.append(q)
            ## Write Process
            qa = slice_qa_embed_data[i].squeeze(1)
            new_memory_value = self.mem.write(correlation_weight, qa, if_memory_write)

            # read_content_embed = torch.tanh(self.read_embed_linear(torch.cat([read_content, q], 1)))
            # pred = self.predict_linear(read_content_embed)
            # predict_logs.append(pred)

        all_read_value_content = torch.cat([value_read_content_l[i].unsqueeze(1) for i in range(seqlen)], 1)
        input_embed_content = torch.cat([input_embed_l[i].unsqueeze(1) for i in range(seqlen)], 1)
        # input_embed_content = input_embed_content.view(batch_size * seqlen, -1)
        # input_embed_content = torch.tanh(self.input_embed_linear(input_embed_content))
        # input_embed_content = input_embed_content.view(batch_size, seqlen, -1)
        
        predict_input = torch.cat([all_read_value_content, input_embed_content], 2)
        read_content_embed = torch.tanh(self.read_embed_linear(predict_input.view(batch_size*seqlen, -1)))

        
        input_embed_content = torch.reshape(input_embed_content, (-1, 50))
        # print(read_content_embed.size())
        # print(input_embed_content.size())
        # print('------------------------')
        student_ability = torch.tanh(self.predict_linear(read_content_embed))
        question_difficulty = torch.tanh(self.predict_linear(input_embed_content))
        pred_ = 3.0 * student_ability - question_difficulty

        pred = self.predict_linear(read_content_embed)
        # predicts = torch.cat([predict_logs[i] for i in range(seqlen)], 1)
        target_1d = target                 # [batch_size * seq_len, 1]
        mask = target_1d.ge(0)               # [batch_size * seq_len, 1]
        # pred_1d = predicts.view(-1, 1)           # [batch_size * seq_len, 1]
        pred_1d = pred_.view(-1, 1)           # [batch_size * seq_len, 1]

        filtered_pred = torch.masked_select(pred_1d, mask)
        
        q_data = q_data.view(-1, 1)
        filtered_target = torch.masked_select(target_1d, mask)
        filtered_student_ability = torch.masked_select(student_ability, mask)
        filtered_question_difficulty = torch.masked_select(question_difficulty, mask)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(filtered_pred, filtered_target)

        return loss, torch.sigmoid(filtered_pred), filtered_target, filtered_student_ability, filtered_question_difficulty