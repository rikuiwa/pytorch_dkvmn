import torch

import utils as utils
import argparse
from model import MODEL
from run import train, test
import numpy as np
import torch.optim as optim
from sklearn import metrics
import seaborn as sns
import matplotlib.pyplot as plt
import torch.nn as nn


from data_loader import DATA_RAW


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=int, default=-1, help='the gpu will be used, e.g "0,1,2,3"')
    parser.add_argument('--max_iter', type=int, default=200, help='number of iterations')
    parser.add_argument('--decay_epoch', type=int, default=20, help='number of iterations')
    parser.add_argument('--test', type=bool, default=False, help='enable testing')
    parser.add_argument('--train_test', type=bool, default=True, help='enable testing')
    parser.add_argument('--show', type=bool, default=True, help='print progress')
    parser.add_argument('--init_std', type=float, default=0.1, help='weight initialization std')
    parser.add_argument('--init_lr', type=float, default=0.01, help='initial learning rate')
    parser.add_argument('--lr_decay', type=float, default=0.75, help='learning rate decay')
    parser.add_argument('--final_lr', type=float, default=1E-5,
                        help='learning rate will not decrease after hitting this threshold')
    parser.add_argument('--momentum', type=float, default=0.9, help='momentum rate')
    parser.add_argument('--maxgradnorm', type=float, default=50.0, help='maximum gradient norm')
    parser.add_argument('--final_fc_dim', type=float, default=50, help='hidden state dim for final fc layer')

    dataset = 'assist2009_updated'

    if dataset == 'assist2009_updated':
        parser.add_argument('--q_embed_dim', type=int, default=50, help='question embedding dimensions')
        parser.add_argument('--batch_size', type=int, default=32, help='the batch size')
        parser.add_argument('--qa_embed_dim', type=int, default=200, help='answer and question embedding dimensions')
        parser.add_argument('--memory_size', type=int, default=5, help='memory size')
        parser.add_argument('--n_question', type=int, default=124, help='the number of unique questions in the dataset')
        parser.add_argument('--seqlen', type=int, default=200, help='the allowed maximum length of a sequence')
        parser.add_argument('--data_dir', type=str, default='./data/assist2009_updated', help='data directory')
        parser.add_argument('--data_name', type=str, default='assist2009_updated', help='data set name')
        parser.add_argument('--load', type=str, default='assist2009_updated', help='model file to load')
        parser.add_argument('--save', type=str, default='assist2009_updated', help='path to save model')

    elif dataset == 'STATICS':
        parser.add_argument('--batch_size', type=int, default=10, help='the batch size')
        parser.add_argument('--q_embed_dim', type=int, default=50, help='question embedding dimensions')
        parser.add_argument('--qa_embed_dim', type=int, default=100, help='answer and question embedding dimensions')
        parser.add_argument('--memory_size', type=int, default=50, help='memory size')
        parser.add_argument('--n_question', type=int, default=1223, help='the number of unique questions in the dataset')
        parser.add_argument('--seqlen', type=int, default=6, help='the allowed maximum length of a sequence')
        parser.add_argument('--data_dir', type=str, default='./data/STATICS', help='data directory')
        parser.add_argument('--data_name', type=str, default='STATICS', help='data set name')
        parser.add_argument('--load', type=str, default='STATICS', help='model file to load')
        parser.add_argument('--save', type=str, default='STATICS', help='path to save model')



    params = parser.parse_args()
    params.lr = params.init_lr
    params.memory_key_state_dim = params.q_embed_dim
    params.memory_value_state_dim = params.qa_embed_dim

    print(params)
    data_path = './data/assist2009_raw/skill_builder_data_corrected.csv'

    dat = DATA_RAW(n_question=params.n_question, seqlen=params.seqlen, separate_char=',')
    # train_data_path = params.data_dir + "/" + "test5.1.txt"

    all_data = dat.get_processed_data(data_path)
    train_q_data, train_qa_data, valid_q_data, valid_qa_data = all_data[0] # first fold

    params.memory_key_state_dim = params.q_embed_dim
    params.memory_value_state_dim = params.qa_embed_dim

    model = MODEL(n_question=params.n_question,
                  batch_size=params.batch_size,
                  q_embed_dim=params.q_embed_dim,
                  qa_embed_dim=params.qa_embed_dim,
                  memory_size=params.memory_size,
                  memory_key_state_dim=params.memory_key_state_dim,
                  memory_value_state_dim=params.memory_value_state_dim,
                  final_fc_dim=params.final_fc_dim)


    model.init_embeddings()
    model.init_params()
    # optimizer = optim.SGD(params=model.parameters(), lr=params.lr, momentum=params.momentum)
    optimizer = optim.Adam(params=model.parameters(), lr=params.lr, betas=(0.9, 0.9))

    if params.gpu >= 0:
        print('device: ' + str(params.gpu))
        torch.cuda.set_device(params.gpu)
        model.cuda()

    all_train_loss = {}
    all_train_accuracy = {}
    all_train_auc = {}
    all_valid_loss = {}
    all_valid_accuracy = {}
    all_valid_auc = {}
    best_valid_auc = 0

    # shuffle_index = np.random.permutation(train_q_data.shape[0])
    # q_data_shuffled = train_q_data[shuffle_index]
    # qa_data_shuffled = train_qa_data[shuffle_index]

    # for idx in range(params.max_iter):
    for idx in range(10):
        train_loss, train_accuracy, train_auc, mask = train(idx, model, params, optimizer, train_q_data, train_qa_data)
        
        print('Epoch %d/%d, loss : %3.5f, auc : %3.5f, accuracy : %3.5f' % (idx + 1, params.max_iter, train_loss, train_auc, train_accuracy))
        valid_loss, valid_accuracy, valid_auc = test(model, params, optimizer, valid_q_data, valid_qa_data)
        print('Epoch %d/%d, valid auc : %3.5f, valid accuracy : %3.5f' % (idx + 1, params.max_iter, valid_auc, valid_accuracy))


        all_train_auc[idx + 1] = train_auc
        all_train_accuracy[idx + 1] = train_accuracy
        all_train_loss[idx + 1] = train_loss
        all_valid_loss[idx + 1] = valid_loss
        all_valid_accuracy[idx + 1] = valid_accuracy
        all_valid_auc[idx + 1] = valid_auc
        #
        # output the epoch with the best validation auc
        if valid_auc > best_valid_auc:
            print('%3.4f to %3.4f' % (best_valid_auc, valid_auc))
            best_valid_auc = valid_auc

    # 能力値の可視化を以下で行う。
    input_q = utils.varible(torch.LongTensor(valid_q_data[0]), params.gpu)
    input_qa = utils.varible(torch.LongTensor(valid_qa_data[0]), params.gpu)
    batch_size = 1
    seqlen = input_q.shape[0]
    q_embed_data = model.q_embed(input_q)
    qa_embed_data = model.qa_embed(input_qa)
    memory_value = nn.Parameter(torch.cat([model.init_memory_value.unsqueeze(0) for _ in range(batch_size)], 0).data)
    model.mem.init_value_memory(memory_value)

    memory_value = model.mem.memory_value
    a = []
    for j in range(5):
        # memoryの初期化
        memory_value = nn.Parameter(torch.cat([model.init_memory_value.unsqueeze(0) for _ in range(batch_size)], 0).data)
        model.mem.init_value_memory(memory_value)
        memory_value = model.mem.memory_value
        student_abilities = []
        # ５０問目までの正答パターンを読み込む
        for i in range(50):
            q = q_embed_data[i]
            q = q.view(1, -1)
            correlation_weight = model.mem.attention(q)
            weight = np.zeros((1, params.memory_size))
            weight[0][j] = 1
            weight = weight.astype(np.float32)
            weight = torch.from_numpy(weight)
            r = torch.mm(weight, memory_value[0])
            k = np.zeros((1, 50))
            k = k.astype(np.float32)
            k = torch.from_numpy(k)
            predict_input = torch.cat([r, k], 1)
            f = torch.tanh(model.read_embed_linear(predict_input))
            student_ability = torch.tanh(model.predict_linear_theta(f))  
            qa = qa_embed_data[i]
            qa = qa.view(1, -1)
            # ここでメモリを更新する
            memory_value = model.mem.write(correlation_weight, qa, False)
            student_abilities.append(student_ability)
        student_abilities = torch.cat([student_abilities[i].unsqueeze(1) for i in range(50)], 1)
        student_abilities.view(1, 50)
        a.append(student_abilities)
    a = torch.cat([a[i].unsqueeze(1) for i in range(5)], 1)
    a = a[0]
    a = a.view(5, 50).cpu().detach().numpy()
    # x軸に正誤の01を表す
    answer = valid_qa_data[0][:50].astype(np.int64)
    for i in range(len(answer)):
        if answer[i] > 123:
            answer[i] = 1
        else:
            answer[i] = 0
    sns.heatmap(a, xticklabels=answer, cmap='RdYlGn')
    plt.show()



    #         best_epoch = idx+1
    #         best_valid_acc = valid_accuracy
    #         best_valid_loss = valid_loss
            # test_loss, test_accuracy, test_auc = test(model, params, optimizer, test_q_data, test_qa_data)
            # print("test_auc: %.4f\ttest_accuracy: %.4f\ttest_loss: %.4f\t" % (test_auc, test_accuracy, test_loss))


    # print("best outcome: best epoch: %.4f" % (best_epoch))
    # print("valid_auc: %.4f\tvalid_accuracy: %.4f\tvalid_loss: %.4f\t" % (best_valid_auc, best_valid_acc, best_valid_loss))
    # print("test_auc: %.4f\ttest_accuracy: %.4f\ttest_loss: %.4f\t" % (test_auc, test_accuracy, test_loss))




if __name__ == "__main__":
    main()
