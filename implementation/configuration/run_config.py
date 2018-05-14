import numpy as np
import torch
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau
from FaceAnonymizer import TrainValidationLoader

from FaceAnonymizer.models.Autoencoder import AutoEncoder
from FaceAnonymizer.models.Decoder import Decoder, LatentDecoder
from FaceAnonymizer.models.DeepFakeOriginal import DeepFakeOriginal
from FaceAnonymizer.models.Encoder import Encoder
from FaceAnonymizer.models.LatentModel import LatentModel
from Preprocessor.FaceExtractor import FaceExtractor
from Preprocessor.ImageDataset import ImageDatesetCombined, LandmarkDataset, CelebA_Landmarks_LowRes
from Preprocessor.Preprocessor import Preprocessor

standart_config = {'batch_size': 64,
                   'num_epoch': 5000,
                   'img_size': (128, 128),
                   'validation_freq': 20,
                   'data_loader': lambda dataset, batch_size: TrainValidationLoader(dataset=dataset,
                                                                                    batch_size=batch_size,
                                                                                    validation_size=0.2,
                                                                                    shuffle=True,
                                                                                    num_workers=12,
                                                                                    pin_memory=True,
                                                                                    drop_last=True),
                   'model': lambda img_size: DeepFakeOriginal(
                       encoder=lambda: Encoder(input_dim=(3,) + img_size,
                                               latent_dim=1024,
                                               num_convblocks=5),
                       decoder=lambda: Decoder(input_dim=512,
                                               num_convblocks=4),
                       auto_encoder=AutoEncoder,
                       loss_function=torch.nn.L1Loss(size_average=True),
                       optimizer=lambda params: Adam(params=params, lr=1e-4),
                       scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                                     verbose=True,
                                                                     patience=100,
                                                                     cooldown=50), ),
                   'preprocessor': lambda: Preprocessor(face_extractor=lambda: FaceExtractor(margin=0.05,
                                                                                             mask_type=np.bool,
                                                                                             mask_factor=10)),
                   'dataset': lambda root_folder, img_size: ImageDatesetCombined(root_folder, size_multiplicator=1,
                                                                                 img_size=img_size)
                   }

alex_config = {'batch_size': 512,
               'num_epoch': 5000,
               'img_size': (128, 128),
               'validation_freq': 20,
               'data_loader': lambda dataset, batch_size: TrainValidationLoader(dataset=dataset,
                                                                                batch_size=batch_size,
                                                                                validation_size=0.2,
                                                                                shuffle=True,
                                                                                num_workers=12,
                                                                                pin_memory=True,
                                                                                drop_last=True),
               'model': lambda: DeepFakeOriginal(
                   encoder=lambda: Encoder(input_dim=(3, 128, 128),
                                           latent_dim=1024,
                                           num_convblocks=5),
                   decoder=lambda: Decoder(input_dim=512,
                                           num_convblocks=4),
                   auto_encoder=AutoEncoder,
                   loss_function=torch.nn.L1Loss(size_average=True),
                   optimizer=lambda params: Adam(params=params, lr=1e-4),
                   scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                                 verbose=True,
                                                                 patience=100,
                                                                 cooldown=50), ),
               'preprocessor': lambda root_folder: Preprocessor(root_folder=root_folder,
                                                                face_extractor=lambda: FaceExtractor(margin=0.05,
                                                                                                     mask_type=np.bool,
                                                                                                     mask_factor=10),
                                                                image_dataset=lambda path: ImageDatesetCombined(
                                                                    dataset=path,
                                                                    img_size=(128, 128)))
               }

landmarks_config = {'batch_size': 64,
                    'num_epoch': 5000,
                    'img_size': (128, 128),
                    'validation_freq': 20,
                    'data_loader': lambda dataset, batch_size: TrainValidationLoader(dataset=dataset,
                                                                                     batch_size=batch_size,
                                                                                     validation_size=0.2,
                                                                                     shuffle=True,
                                                                                     num_workers=12,
                                                                                     pin_memory=True,
                                                                                     drop_last=True),
                    'model': lambda img_size: LatentModel(
                        decoder=lambda: LatentDecoder(72 * 2+8*8*3),
                        loss_function=torch.nn.L1Loss(size_average=True),
                        optimizer=lambda params: Adam(params=params, lr=1e-4),
                        scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                                      verbose=True,
                                                                      patience=100,
                                                                      cooldown=50)),

                    'preprocessor': lambda: Preprocessor(face_extractor=lambda: FaceExtractor(margin=0.05,
                                                                                              mask_type=np.bool,
                                                                                              mask_factor=10)),
                    'dataset': lambda root_folder, img_size: LandmarkDataset(root_folder=root_folder,
                                                                             size_multiplicator=1,
                                                                             img_size=img_size)}

lm_lowres_config = landmarks_config.copy()
lm_lowres_config['dataset'] = lambda root_folder, img_size: CelebA_Landmarks_LowRes(root_folder=root_folder,
                                                                                    size_multiplicator=1,
                                                                                    target_img_size=img_size)

current_config = lm_lowres_config
