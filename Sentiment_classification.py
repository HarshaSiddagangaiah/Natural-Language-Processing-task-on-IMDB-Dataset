# -*- coding: utf-8 -*-
"""HW4_sentiment-classification.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1e8vMZiWZkKzzQ_c_SvibsS-XHZqOgdcl
"""

# Import necessary libraries
import json
from nltk import word_tokenize
import numpy as np
import glob
from tqdm import tqdm
import nltk

# Uploading the training data and GLoVe Embedding to your Google Drive

# Connecting this Google Colab to your Google Drive storage
from google.colab import drive
drive.mount('/content/drive')

# Check if an Nvidia GPU is available
# https://www.tutorialspoint.com/google_colab/google_colab_using_free_gpu.htm
!nvidia-smi

def load_glove(path, dim=300):
    """
    GLoVe embedding is a way to map a word into a fixed-dimension vector.
    This function load the GLoVe embedding
    :param path:
    :param dim: dimesion of the word vector
    :return: a 2D numpy matrix and a dictionary that maps a word into index in the numpy matrix
    """
    matrix = []
    word_index = dict()

    # Adding a zero vector of the same size as "<PAD>" token, index of 0
    # Adding a random vector of the same size as "<UNK>" token, index of 1

    matrix.append([0.] * dim)
    matrix.append([0.] * dim)
    word_index['<PAD>'] = 0
    word_index['<UNK>'] = 1
    # Load from glove
    #
    with open(path, encoding='latin-1') as f:
        lines = f.readlines()
        for l in lines:
            parts = l.split(' ')
            vector = [float(x) for x in parts[1:]]
            matrix.append(vector)
            word_index[parts[0]] = len(word_index)

    matrix = np.array(matrix, dtype=np.float)
    return matrix, word_index

# Actually call the function to load the GLoVe
import os
matrix, word_index = load_glove('drive/MyDrive/temp/glove.6B.50d.txt', 50)

# More libraries and download data for the word tokenizer.

import torch
from torch.utils.data import Dataset
import nltk
nltk.download('punkt')
from nltk import word_tokenize

# A "Dataset" class manage the loading/preprocessing/sampling/packaging of input data
# It is used by a "DataLoader" in the later part of the code
class ImdbDataset(Dataset):

    def __init__(self, data_file_path, word_index, max_length):
        super(ImdbDataset, self).__init__()
        self.word_index = word_index
        # Paragraph max length
        self.ML = max_length
        # Load data from data_file_path
        self.data = load_json(data_file_path)
        # Target is an integer representing a class
        # E.g. label="positive" -> target=1
        #      label="negative" -> target=0
        self.target_map ={
            'positive': 1,
            'negative': 0
        }


    def __len__(self):
        # Returning the length of the dataset, basically, the number of data points
        return len(self.data)

    def all_targets(self):
        # Returning all the targets of the dataset, orderly.
        return [x['target'] for x in self.data]

    def __getitem__(self, idx):
        """
        :param idx: an index of a data point from the dataset.
        """
        # Just picking it from self.data
        item = self.data[idx]

        # Tokenize and initialize the target for each data point.
        # Tokenize paragraphs into words and punctuations
        # Each of the splitted string is called a "token"

        tokens = word_tokenize(item['text'].lower())

        # Indices stores the index of the token in the GLoVe embedding matrix
        indices = []
        for x in tokens:
          if x in word_index:
              indices.append(word_index[x])
          else:
              indices.append(word_index['<UNK>'])

        # Croping the sentence upto a certain length
        indices = indices[:self.ML]
        target = self.target_map[item['label']]

        # Pad sentence: append <pad_token_index> to the sentence which is shorter than maximum length.
        l = len(indices)
        if l < self.ML:
            indices += [0 for _ in range(self.ML - l)] # 0 is the index of a dummy pad token

        # Make sure that the sentence is cropped and padded correctly
        assert len(indices) == self.ML
        return {
            'indices': indices,
            'target': target
        }

    @staticmethod
    def pack(items):
        """
        :param items: list of items, each item is an object returned from __getitem__ function
        :return:
        """
        # Pack item into batch
        # Each batch is a dictionary (similar to each item)
        batch = {
            'indices': torch.LongTensor([x['indices'] for x in items]),
            'target': torch.LongTensor([x['target'] for x in items])
        }
        return batch

# Calculating the accuracy score

from sklearn.metrics import accuracy_score
def metrics(predictions: list, targets: list):
    """

    :param predictions:
    :param targets:
    :return:
    """
    return accuracy_score(targets, predictions)

def load_json(path):
    """
    Load a json file, return the data
    :param path:
    :return:
    """
    print('Loading', path, end=' ')
    with open(path, 'r', encoding='latin-1') as f:
        data = json.load(f)
    print(len(data))
    return data

# Defining hyperparameters
# This help the finetuning more organized

# ADJUSTING THESE HYPERPARAMETERS

class Argument:
  n_class= 2    # Number of classes (dont change this)
  max_length= 384  # Maximum length of the text will be feed to the model    Try [64:1024]

  glove= 'drive/MyDrive/temp/glove.6B.50d.txt'  # GLoVe embedding version, try all given versions
  
  # Model arguments
  dropout= 0.2          # Dropout rate          Try [0.2:0.8]
  hidden_size= 128      # Hidden layer size     Try [64:512]
  kernel_size= 5        # CNN kernel size       Try [3,5,7,9,11]

  # Training arguments
  epoch= 30            # Number of training epochs.  Try [20:200]
  lr= 0.0075              # Learning rate               Try [1e-2:1e-4]
  batch_size= 48       # Batch size                  Try [32:128]
  optimizer= torch.optim.SGD        # Optimizer       Try [SGD, Adam, Adadelta]

  
args = Argument

# Setup the CUDA device
os.environ['CUDA_VISIBLE_DEVICES'] = "0"
args = Argument
args.device = 'cuda' if torch.cuda.is_available() else 'cpu'

# Make sure the cuda is used
print('Using device: ', args.device)



import torch.nn as nn

# This is a simple version of the CNN for text classification proposed by Yoon Kim
# Access the paper here: https://arxiv.org/pdf/1408.5882.pdf
class BaseModel(nn.Module):

    def __init__(self, embedding_matrix, args):
        """
        :param: embedding_matrix: the GLoVe embedding matrix
        :param: args: an object of "Argument" class, this class is defined in the later part of the code
        """

        super(BaseModel, self).__init__()
        self.device = args.device
        hidden_size = args.hidden_size

        # creating an embedding module
        N, D = embedding_matrix.shape
        self.embedding = nn.Embedding(N, D, _weight=torch.FloatTensor(embedding_matrix))

        # Disabling gradient update of embedding
        self.embedding.weight.requires_grad = False
        self.embedding_dim = D


        # Define the layers
        self.conv = nn.Conv1d(D, hidden_size, kernel_size=args.kernel_size)
        self.max_pool = nn.MaxPool1d(args.max_length - args.kernel_size + 1)
        self.fc = nn.Sequential(
            nn.Tanh(),
            nn.Dropout(args.dropout),
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Dropout(args.dropout),
            nn.Linear(args.hidden_size, args.n_class)
        )

    def forward(self, batch):
        # B denotes batch_size
        # L denotes sentence length
        # D denotes vector dimension

        # Get embedding
        embedding = self.embedding(batch['indices'].to(self.device))  # size of (B x L x D)
        # print('| embedding', tuple(embedding.shape))
        x = embedding.transpose(dim0=1, dim1=2)  # B x D x L
        # Feed through the neural network
        conv_x = self.conv(x)  # B x D x L
        # print('| conv_x', tuple(conv_x.shape))

        max_pool = self.max_pool(conv_x) # B x D x 1
        max_pool = max_pool.squeeze(dim=2) # B x D
        # print('| max_pool', tuple(max_pool.shape))

        logits = self.fc(max_pool)

        # print('| logits', tuple(logits.shape))


        # Calculating the prediction
        predictions = torch.argmax(logits, dim=-1)

        return logits, predictions

# Creating a dataloader object
from torch.utils.data import DataLoader

# Shorter = faster training, Longer=(possibly) higher accuracy
train_dataset = ImdbDataset('drive/MyDrive/temp/train.json', word_index, args.max_length)
dev_dataset = ImdbDataset('drive/MyDrive/temp/dev.json', word_index, args.max_length)

train_dl = DataLoader(train_dataset, 
                      batch_size=args.batch_size, # Mini-batch
                      shuffle=True,               # Stochastic 
                      num_workers=2,              # 4 external processes dedicated for preprocessing data
                      collate_fn=ImdbDataset.pack)# Pack separate samples into a batch
dev_dl = DataLoader(dev_dataset, 
                    batch_size=args.batch_size, 
                    shuffle=False,                # Don't shuffle in evaluation
                    num_workers=2,
                    collate_fn=ImdbDataset.pack)
# Loading GLoVe embedding
embedding_matrix, _ = load_glove(args.glove, dim=50)

# Creating the model object
model = BaseModel(embedding_matrix, args)
# Sending the model to GPU
model.to(args.device)

# Selecting all trainable parameters
params = [x for x in model.parameters() if x.requires_grad == True]
# Creating an optimizer object
optimizer = args.optimizer(params, lr=args.lr)
# Printing out to see the model architecture
print(model)

from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np


def train_and_evaluate(model, train_dl, dev_dl, optimizer, args):
    """
    Implementation of stochastic gradient decent
    """
    loss_fn = torch.nn.CrossEntropyLoss()
    global dev_loss_list
    global train_loss_list
    global train_acc_list
    global dev_acc_list
    dev_loss_list = []
    train_loss_list = []
    train_acc_list = []
    dev_acc_list = []

    for e in range(args.epoch):
        train_loss = 0
        dev_loss = 0

        # Training
        model.train()
        train_targets, train_preds = [], []
        for batch in tqdm(train_dl, desc='Train'):
            optimizer.zero_grad()
            logits, preds = model(batch)
            train_preds += preds.detach().cpu().numpy().tolist()
            targets = batch['target'].numpy().tolist()
            train_targets += targets
            loss = loss_fn(logits, batch['target'].to(args.device))
            loss.backward()
            # Printing loss 
            train_loss += loss.item()
            optimizer.step()

        avg_train_loss = (train_loss/len(train_dl))
        print("Train loss:", avg_train_loss )
        train_loss_list.append(avg_train_loss)
        train_acc = metrics(train_preds, train_targets)
        train_acc_list.append(train_acc)

        # Printing train_acc
        print(" Training acc:", train_acc)

        # Evaluation
        model.eval()
        dev_targets, dev_preds = [], []
        for batch in tqdm(dev_dl, desc="Dev"):
            _, preds = model(batch)
            dev_preds += preds.detach().cpu().numpy().tolist()
            targets = batch['target'].numpy().tolist()
            dev_targets += targets
            #computing dev loss and printing
            loss = loss_fn(_, batch['target'].to(args.device))
            dev_loss += loss.item()
        
        avg_dev_loss = (dev_loss/len(dev_dl))
        print("Dev loss:", avg_dev_loss )
        dev_loss_list.append(avg_dev_loss)
        dev_acc = metrics(dev_preds, dev_targets)
        dev_acc_list.append(dev_acc)
        # printing dev_acc
        print(" Dev acc:", dev_acc)

        # Logging the epoch and scores
        print(f'Epoch {e} Train={train_acc:.4f} Dev={dev_acc:.4f}')
# Actual training
train_and_evaluate(model, train_dl, dev_dl, optimizer, args)

# Adding more code to print out logging 
 # Using visualization library like matplotlib to visualize training/evaluation process
 #    such as training loss, training accuracy, development loss, development accuracy

import matplotlib.pyplot as plt

# learning curve for loss function on training and development data

plt.plot(range(0,args.epoch), train_loss_list, 'g', label='Training loss')
plt.plot(range(0,args.epoch), dev_loss_list, 'b', label='Dev loss')
plt.title('Learning curve for loss on Train and Dev')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()
plt.show()

# Learning curves for accuracy on training and development data


plt.plot(range(0,args.epoch), train_acc_list, 'g', label='Training acc')
plt.plot(range(0,args.epoch), dev_acc_list, 'b', label='Dev acc')
plt.title('Learning curves for acc on Train and Dev')
plt.xlabel('Epochs')
plt.ylabel('Accuracy')
plt.legend()
plt.show()

