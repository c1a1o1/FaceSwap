import numpy as np
import torch
from PIL.Image import LANCZOS, BICUBIC
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torchvision.transforms import ToTensor

from FaceAnonymizer import TrainValidationLoader

from FaceAnonymizer.models.Autoencoder import AutoEncoder
from FaceAnonymizer.models.Decoder import Decoder, LatentDecoder
from FaceAnonymizer.models.DeepFakeOriginal import DeepFakeOriginal
from FaceAnonymizer.models.Encoder import Encoder
from FaceAnonymizer.models.LatentModel import LatentModel
from Preprocessor.FaceExtractor import FaceExtractor
from Preprocessor.ImageDataset import ImageDatesetCombined, LandmarksDataset, LandmarksLowResDataset, \
    LandmarksHistDataset, LandmarksHistAnnotationsDataset, LandmarksLowResAnnotationsDataset
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
                                                                                 img_size=img_size),
                   'img2latent_bridge:': lambda extracted_face, extracted_information, img_size:
                   ToTensor()(extracted_face.resize(img_size, resample=BICUBIC)).unsqueeze(0).cuda()
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
               'preprocessor': lambda: Preprocessor(face_extractor=lambda: FaceExtractor(margin=0.05,
                                                                                             mask_type=np.bool,
                                                                                             mask_factor=10)),
               }

####### config for using only landmarks as input
# todo move the input dimensionality of the network to somewhere als as parameter
# dim = 72*2
landmarks_config = {'batch_size': 512,
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
                        decoder=lambda: LatentDecoder(72 * 2 + 8 * 8 * 3),
                        loss_function=torch.nn.L1Loss(size_average=True),
                        optimizer=lambda params: Adam(params=params, lr=1e-4),
                        scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                                      verbose=True,
                                                                      patience=100,
                                                                      cooldown=50)),

                    'preprocessor': lambda: Preprocessor(face_extractor=lambda: FaceExtractor(margin=0.05,
                                                                                              mask_type=np.bool,
                                                                                              mask_factor=10)),
                    'dataset': lambda root_folder, img_size: LandmarksDataset(root_folder=root_folder,
                                                                              size_multiplicator=1,
                                                                              img_size=img_size),
                    'img2latent_bridge:': lambda extracted_face, extracted_information, img_size: torch.from_numpy(
                        np.reshape(
                            (np.array(extracted_information.landmarks) / extracted_information.size_fine).tolist(),
                            -1).astype(np.float32)).unsqueeze(0).cuda()}

####### config for using landmarks as well as a low res image as input
# dim = 72+2+8+8+3
lm_lowres_config = landmarks_config.copy()
lm_lowres_config['dataset'] = lambda root_folder, img_size: LandmarksLowResDataset(root_folder=root_folder,
                                                                                   size_multiplicator=1,
                                                                                   target_img_size=img_size)
lm_lowres_config['img2latent_bridge'] = lambda extracted_face, extracted_information, img_size: (
    torch.from_numpy(
        np.append(
            np.reshape((np.array(extracted_information.landmarks) / extracted_information.size_fine).tolist(),
                       -1),
            # todo this is really ugly
            ToTensor()(
                extracted_face.resize(img_size, BICUBIC).resize((8, 8), BICUBIC)).numpy().flatten())
            .astype(np.float32))
        .unsqueeze(0).cuda()
)

###### config for using landmarks as well as a histogram of the target as input
lm_hist_config = landmarks_config.copy()
lm_hist_config['dataset'] = lambda root_folder, img_size: LandmarksHistDataset(root_folder=root_folder,
                                                                               size_multiplicator=1,
                                                                               img_size=img_size)
lm_hist_config['img2latent_bridge'] = lambda extracted_face, extracted_information, img_size: (
    torch.from_numpy(
        np.append(
            np.reshape((np.array(extracted_information.landmarks) / extracted_information.size_fine).tolist(),
                       -1),
            # todo this is really ugly
            np.array(extracted_face.resize(img_size, BICUBIC).histogram()).flatten() / (
                    img_size[0] * img_size[1] * 3))
            .astype(np.float32))
        .unsqueeze(0).cuda()
)

lm_hist_config['model'] = lambda img_size: LatentModel(
    decoder=lambda: LatentDecoder(72 * 2 + 768),
    loss_function=torch.nn.L1Loss(size_average=True),
    optimizer=lambda params: Adam(params=params, lr=1e-4),
    scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                  verbose=True,
                                                  patience=100,
                                                  cooldown=50))

###### config for using landmarks as well as a histogram as well as annotations of the target as input
lm_hist_annotations_config = lm_hist_config.copy()
lm_hist_annotations_config['dataset'] = lambda root_folder, img_size: LandmarksHistAnnotationsDataset(
    root_folder=root_folder,
    size_multiplicator=1,
    img_size=img_size)

lm_hist_annotations_config['model'] = lambda img_size: LatentModel(
    decoder=lambda: LatentDecoder(72 * 2 + 768 + 40),
    loss_function=torch.nn.L1Loss(size_average=True),
    optimizer=lambda params: Adam(params=params, lr=1e-4),
    scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                  verbose=True,
                                                  patience=100,
                                                  cooldown=50))

lm_lowres_annotations_config = lm_lowres_config.copy()
lm_lowres_annotations_config['dataset'] = lambda root_folder, img_size: LandmarksLowResAnnotationsDataset(
    root_folder=root_folder,
    size_multiplicator=1,
    target_img_size=img_size)

lm_lowres_annotations_config['model'] = lambda img_size: LatentModel(
    decoder=lambda: LatentDecoder(72 * 2 + 8 * 8 * 3 + 40),
    loss_function=torch.nn.L1Loss(size_average=True),
    optimizer=lambda params: Adam(params=params, lr=1e-4),
    scheduler=lambda optimizer: ReduceLROnPlateau(optimizer=optimizer,
                                                  verbose=True,
                                                  patience=100,
                                                  cooldown=50))

current_config = lm_lowres_config  # lm_lowres_annotations_config  # lm_hist_annotations_config  # lm_hist_config  #
