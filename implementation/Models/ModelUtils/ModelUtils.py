from abc import abstractmethod, ABCMeta
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


class CustomModule(nn.Module):
    """
    Use this custom module class in combination with the combined model class below to enable auto loading and saving.
    You can use this class just like a normal nn.Module.
    """

    @abstractmethod
    def forward(self, *input):
        raise NotImplementedError

    @property
    def is_cuda(self):
        """
        Check if model parameters are allocated on the GPU.
        """
        return next(self.parameters()).is_cuda

    def save(self, path):
        """
        Save model with its parameters to the given path. Conventionally the
        path should end with "*.model".

        Inputs:
        - path: path string
        """
        print('Saving model... %s' % path)
        torch.save(self.state_dict(), path)

    def load(self, path):
        """
        Load model with its parameters from the given path. Conventionally the
        path should end with "*.model".

        Inputs:
        - path: path string
        """
        print('Loading model... %s' % path)
        self.load_state_dict(torch.load(path, map_location=lambda storage, loc: storage))

    @staticmethod
    def weights_init(m):
        classname = m.__class__.__name__
        if classname.find('Conv') != -1:
            m.weight.data.normal_(0.0, 0.02)
        elif classname.find('BatchNorm') != -1:
            m.weight.data.normal_(1.0, 0.02)
            m.bias.data.fill_(0)


class CombinedModel(metaclass=ABCMeta):
    """
    Use this abstract class for your whole model for integration in our framework.
    This enables:
        auto save/load
        logging of the architecture
        logging of images
        logging of losses and other values
        automatic validation/train mode
    """

    @abstractmethod
    def get_modules(self):
        """
        :return: a list of modules that should be auto loaded and saved; these modules need to inherit from CustomModel
        """
        raise NotImplementedError

    @abstractmethod
    def get_model_names(self):
        """
        :return: a list with names of the modules specified in get_modules | these are the names used for saving and
        loading
        """
        raise NotImplementedError

    @abstractmethod
    def get_remaining_modules(self):
        """
        :return: this additional list is used for logging purposes | all modules (get_modules + get_remaining_modules)
        will be logged to the tensorboard
        """
        raise NotImplementedError

    @abstractmethod
    def train(self, train_data_loader, batch_size, validate, **kwargs):
        """
        This method is used to train the model
        :param train_data_loader: data_loader with one epoch of data
        :param batch_size: size of one batch
        :param validate: indicates if the function should run in evaluation mode without training
        :param kwargs: additional variables needed for a individual model
        :return: returns a tuple of a dict (containing values logged to the tensorboard) and a list of images (also
        logged to the tensorboard)
        """
        raise NotImplementedError

    @abstractmethod
    def anonymize(self, extracted_face, extracted_information):
        """
        This function is used to anonymize a incoming picture
        :param extracted_face: extracted face (by the face extractor) in RGB
        :param extracted_information: additional information possibly needed by the network like landmarks)
        :return: returns a anonymized version of the input image
        """
        raise NotImplementedError

    def log(self, logger, epoch, log_info, images, log_images=False):
        """
        function called by the Trainer class to log information provieded by the train method of this class
        :param logger: logger used to log
        :param epoch: current epoch
        """
        logger.log_values(epoch=epoch, values=log_info)
        logger.log_fps(epoch=epoch)

        # log images
        if log_images:
            self.log_images(logger, epoch, images, validation=False)
        logger.save_model(epoch)

    def log_validation(self, logger, epoch, log_info, images):
        logger.log_values(epoch=epoch, values=log_info)
        self.log_images(logger, epoch, images, validation=True)

    @abstractmethod
    def log_images(self, logger, epoch, images, validation):
        """
        this function is called by the log method of this class if images should be logged
        This has to be implemented by each Model itself because the images can be in any format
        postprocessing my be needed
        :param logger: Logger used for logging (look into LoggingUtils.py)
        :param epoch: current epoch
        :param images: images that should be logged
        :param validation: are this validation images | indicates the tag for the tensorboard
        """
        raise NotImplementedError

    def __str__(self):
        # tensorbord uses markup to display text, we use two tabs in front of each line to mark it as code
        string = "\t\t"
        for model in self.get_modules():
            string += str(model) + '\n'

        for module in self.get_remaining_modules():
            string += str(module) + '\n'

        string = string.replace('\n', '\n\t\t')
        return string

    def set_train_mode(self, mode):
        """
        sets the train mode of each CustomModule
        :param mode: current train mode (validation or training)
        :return:
        """
        for model in self.get_modules():
            model.train(mode)
        torch.set_grad_enabled(mode)

    def save_model(self, path):
        """
        save all CustomModules to the specified path
        :param path: location where you want to save the modules
        """
        path = Path(path)
        path = path / 'model'
        path.mkdir(parents=True, exist_ok=True)
        for name, model in zip(self.get_model_names(), self.get_modules()):
            if type(model) is nn.DataParallel:
                model.module.save(path / (name + '.model'))
            else:
                model.save(path / (name + '.model'))

    def load_model(self, path):
        """
        Load all CostumModules from the specified location
        :param path: location you want to load from
        :return:
        """
        path = Path(path)
        for name, model in zip(self.get_model_names(), self.get_modules()):
            model.load(path / (name + '.model'))


class ConvBlock(nn.Module):
    """Convolution followed by a LeakyReLU"""

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=5,
                 stride=2):
        """
        Initialize a ConvBlock.

        Inputs:
        - in_channels: Number of channels of the input
        - out_channels: Number of filters
        - kernel_size: Size of a convolution filter
        - stride: Stride of the convolutions
        """
        super(ConvBlock, self).__init__()
        # spatial size preserving padding: Padding = (Filter-1)/2
        self.conv = nn.Conv2d(in_channels=in_channels,
                              out_channels=out_channels,
                              kernel_size=kernel_size,
                              stride=stride,
                              padding=(kernel_size - 1) // 2)
        self.leaky = nn.LeakyReLU(negative_slope=0.1,
                                  inplace=True)

    def forward(self, x):
        """
        Forward pass of the ConvBlock. Should not be called
        manually but by calling a model instance directly.

        Inputs:
        - x: PyTorch input Variable
        """
        x = self.conv(x)
        x = self.leaky(x)

        return x


class UpscaleBlock(nn.Module):
    """Scales image up"""

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=3,
                 stride=1):
        """
        Initialize a UpscaleBlock.

        Inputs:
        - in_channels: Number of channels of the input
        - out_channels: Number of filters
        - kernel_size: Size of a convolution filter
        - stride: Stride of the convolutions
        """
        super(UpscaleBlock, self).__init__()
        self.conv = nn.Conv2d(in_channels=in_channels,
                              out_channels=out_channels * 4,  # compensate PixelShuffle dimensionality reduction
                              kernel_size=kernel_size,
                              stride=stride,
                              padding=(kernel_size - 1) // 2)
        self.leaky = nn.LeakyReLU(negative_slope=0.1,
                                  inplace=True)
        self.pixel_shuffle = nn.PixelShuffle(2)

    def forward(self, x):
        """
        Forward pass of the UpscaleBlock. Should not be called
        manually but by calling a model instance directly.

        Inputs:
        - x: PyTorch input Variable
        """
        x = self.conv(x)
        x = self.leaky(x)
        x = self.pixel_shuffle(x)
        return x


class Flatten(nn.Module):
    """Flatten images"""

    def forward(self, input):
        return input.view(input.size(0), -1)


class View(nn.Module):
    """
    Reshape tensor
    https://discuss.pytorch.org/t/equivalent-of-np-reshape-in-pytorch/144/5
    """

    def __init__(self, *shape):
        super(View, self).__init__()
        self.shape = shape

    def forward(self, input):
        return input.view(self.shape)


class ConvBlockBlock(nn.Sequential):
    """
    Just a wrapper arround the ConvBlock to stack multiples blocks
    """

    def __init__(self, channels_in, num_channels_first_layer=128, depth=4):
        block_list = [ConvBlock(channels_in, num_channels_first_layer)]
        for i in range(1, depth):
            block_list.append(
                ConvBlock(num_channels_first_layer * (2 ** (i - 1)), num_channels_first_layer * (2 ** i)))
        super().__init__(*block_list)


class UpscaleBlockBlock(nn.Sequential):
    """
    Just a wrapper arround the UpscaleBlock to stack multiples blocks
    """

    def __init__(self, channels_in, num_channels_first_layer=256, depth=3):
        block_list = [UpscaleBlock(channels_in, num_channels_first_layer)]
        for i in range(1, depth):
            block_list.append(
                UpscaleBlock(num_channels_first_layer // (2 ** (i - 1)), num_channels_first_layer // (2 ** i)))
        super().__init__(*block_list)


class RandomNoiseGenerator:
    """
    This class can be used to generate gaussian and uniform noise directly as tensor with the correct batchsize
    https://github.com/github-pengge/PyTorch-progressive_growing_of_gans/blob/master/utils/data.py
    """

    def __init__(self, size, noise_type='gaussian'):
        self.size = size
        self.noise_type = noise_type.lower()
        assert self.noise_type in ['gaussian', 'uniform']
        self.generator_map = {'gaussian': np.random.randn, 'uniform': np.random.uniform}
        if self.noise_type == 'gaussian':
            self.generator = lambda s: np.random.randn(*s)
        elif self.noise_type == 'uniform':
            self.generator = lambda s: np.random.uniform(-1, 1, size=s)

    def __call__(self, batch_size):
        """
        returns random tensor
        :param batch_size: the size of the resulting random tensor
        :return: random float32 tensor
        """
        return torch.from_numpy(self.generator([batch_size, self.size]).astype(np.float32))


def norm_img(img):
    """
    Normalize image via min max inplace
    :param img: Tensor image
    """
    _min, _max = float(img.min()), float(img.max())
    img.clamp_(min=_min, max=_max)
    img.add_(-_min).div_(_max - _min + 1e-5)
