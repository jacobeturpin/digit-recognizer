"""An application of PyTorch on a digit recognizing dataset"""

import argparse
import numpy as np
import pandas as pd

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import torch.optim as optim

from PIL import Image
import torchvision


class PredictCsvDataset(Dataset):

    def __init__(self, csv_path, height, width, transforms=None):
        """
        Args:
            df (pd.DataFrame): path to csv file
            height (int): height of image
            width (int): width of image
            transforms: torch transformations and tensor conversions
        """
        self.data = pd.read_csv(csv_path)
        self.height = height
        self.width = width
        self.transforms = transforms

    def __getitem__(self, item):

        image_data = np.asarray(self.data.iloc[item], dtype='uint8')
        img_as_np = np.reshape(image_data, (28, 28))

        img_as_img = Image.fromarray(img_as_np)
        img_as_img = img_as_img.convert('L')

        if self.transforms is not None:
            img_as_tensor = self.transforms(img_as_img)

        return img_as_tensor

    def __len__(self):
        return len(self.data.index)


class PandasImageDataset(Dataset):

    def __init__(self, df, height, width, transforms=None):
        """
        Args:
            df (pd.DataFrame): path to csv file
            height (int): height of image
            width (int): width of image
            transforms: torch transformations and tensor conversions
        """
        self.data = df

        self.labels = np.asarray(self.data.iloc[:, 0])
        self.height = height
        self.width = width
        self.transforms = transforms

    def __getitem__(self, item):
        single_image_label = self.labels[item]

        image_data = np.asarray(self.data.iloc[item, 1:], dtype='uint8')
        img_as_np = np.reshape(image_data, (28, 28))

        img_as_img = Image.fromarray(img_as_np)
        img_as_img = img_as_img.convert('L')

        if self.transforms is not None:
            img_as_tensor = self.transforms(img_as_img)

        return img_as_tensor, single_image_label

    def __len__(self):
        return len(self.data.index)


class Net(nn.Module):

    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 10, kernel_size=5)
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, 10)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()

    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)

        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, (batch_idx + 1) * args.batch_size, len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.item()
            ))


def test(args, model, device, test_loader):
    model.eval()

    test_loss = 0
    correct = 0

    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)

            output = model(data)
            test_loss += F.nll_loss(output, target, size_average=False).item()
            pred = output.max(1, keepdim=True)[1]

            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)
    ))


def predict(args, model, device, submission_loader):
    """Takes input data and creates predictions based upon model

    Args:
         args (object): set of arguments defining model
         model (Net): torch model
         device (torch.device): device where tensors are allocated
         submission_loader (DataLoader): object used to load data into predictions

    Returns:
        pd.DataFrame of predictions for input data
    """
    model.eval()

    predictions = []

    with torch.no_grad():
        for idx, data in enumerate(submission_loader):
            output = model(data)
            pred_batch = output.max(1, keepdim=True)[1]
            predictions.extend(pred_batch.tolist())

    return predictions


def main():
    # Training Settings
    parser = argparse.ArgumentParser(description='PyTorch Digit Recognizer')

    parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=10, metavar='N',
                        help='number of epochs to train (default: 10)')
    parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                        help='learning rate (default: 0.01)')
    parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                        help='SGD momentum (default: 0.5)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                        help='how many batches to wait before logging training status')
    args = parser.parse_args()

    use_cuda = not args.no_cuda and torch.cuda.is_available()

    # torch.manual_seed(args.seed)

    device = torch.device("cuda" if use_cuda else "cpu")

    kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

    df = pd.read_csv('train.csv')
    df = df.sample(frac=1).reset_index(drop=True)
    train_size = int(len(df.index) * 0.9)

    train_set = df.iloc[:train_size].reset_index(drop=True)
    test_set = df.iloc[train_size:].reset_index(drop=True)

    print(len(train_set.index))

    train_dataset = PandasImageDataset(train_set, 28, 28,
                                       torchvision.transforms.Compose([
                                           torchvision.transforms.ToTensor(),
                                           torchvision.transforms.Normalize((0.1307,), (0.3081,))
                                       ]))

    test_dataset = PandasImageDataset(test_set, 28, 28,
                                      torchvision.transforms.Compose([
                                          torchvision.transforms.ToTensor(),
                                          torchvision.transforms.Normalize((0.1307,), (0.3081,))
                                      ]))

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size, shuffle=True, **kwargs)

    test_loader = DataLoader(
        test_dataset,
        batch_size=args.test_batch_size, shuffle=True, **kwargs)

    submission_loader = DataLoader(
        PredictCsvDataset('test.csv', 28, 28,
                          torchvision.transforms.Compose([
                               torchvision.transforms.ToTensor(),
                               torchvision.transforms.Normalize((0.1307,), (0.3081,))
                           ])),
        batch_size=args.test_batch_size, shuffle=False, **kwargs)

    model = Net().to(device)
    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

    for epoch in range(1, args.epochs + 1):
        train(args, model, device, train_loader, optimizer, epoch)
        test(args, model, device, test_loader)

    # torch.save(model.state_dict(), '.')

    predictions = predict(args, model, device, submission_loader)
    pred_df = pd.DataFrame(predictions, columns=['Label'])
    pred_df.index += 1
    pred_df.index.names = ['ImageId']
    pred_df.to_csv('submission.csv')


if __name__ == '__main__':
    main()
