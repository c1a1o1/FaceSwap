import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from Configuration.config_general import ARRAY_CELEBA_LANDMARKS_MEAN, ARRAY_CELEBA_LANDMARKS_COV
from Models.CGAN.Discriminator import Discriminator
from Models.CGAN.Generator import Generator
from Models.ModelUtils.ModelUtils import CombinedModel


class CGAN(CombinedModel):
    def __init__(self, **kwargs):
        self.z_dim = kwargs.get('z_dim', 100)
        self.y_dim = kwargs.get('y_dim', 10)
        self.img_dim = kwargs.get('img_dim', (64, 64, 3))
        path_to_y_mean = kwargs.get('y_mean', ARRAY_CELEBA_LANDMARKS_MEAN)
        path_to_y_cov = kwargs.get('y_cov', ARRAY_CELEBA_LANDMARKS_COV)
        lrG = kwargs.get('lrG', 0.0002)
        lrD = kwargs.get('lrD', 0.0002)
        beta1 = kwargs.get('beta1', 0.5)
        beta2 = kwargs.get('beta2', 0.999)

        # self.G = LatentDecoderGAN(input_dim=self.z_dim + self.y_dim)
        self.G = Generator(input_dim=(self.z_dim, self.y_dim), output_dim=self.img_dim, ngf=64)
        self.D = Discriminator(y_dim=self.y_dim, input_dim=self.img_dim, ndf=64)

        self.G_optimizer = optim.Adam(self.G.parameters(), lr=lrG, betas=(beta1, beta2))
        self.D_optimizer = optim.Adam(self.D.parameters(), lr=lrD, betas=(beta1, beta2))

        self.BCE_loss = nn.BCELoss()

        # gaussian distribution of our landmarks
        self.landmarks_mean = np.load(path_to_y_mean)
        self.landmarks_cov = np.load(path_to_y_cov)
        # self.landmarks_mean = torch.from_numpy(self.landmarks_mean)
        # self.landmarks_cov = torch.from_numpy(self.landmarks_cov)
        # self.distribution = MultivariateNormal(loc=self.landmarks_mean.type(torch.float64),
        #                                        covariance_matrix=self.landmarks_cov.type(torch.float64))

        if torch.cuda.is_available():
            self.cuda = True
            self.G.cuda()
            self.D.cuda()
            self.BCE_loss.cuda()

    def __str__(self):
        string = super().__str__()
        string += str(self.G_optimizer) + '\n'
        string += str(self.D_optimizer) + '\n'
        string += str(self.BCE_loss) + '\n'
        string = string.replace('\n', '\n\n')
        return string

    def _train(self, data_loader, batch_size, **kwargs):
        # indicates if the graph should get updated
        validate = kwargs.get('validate', False)

        # sum the loss for logging
        g_loss_summed, d_loss_summed = 0, 0
        iterations = 0

        # Label vectors for loss function
        label_real, label_fake = (torch.ones(batch_size, 1, 1, 1), torch.zeros(batch_size, 1, 1, 1))
        if self.cuda:
            label_real, label_fake = label_real.cuda(), label_fake.cuda()

        for images, features in data_loader:
            # generate random vector
            z = torch.randn((batch_size, self.z_dim))
            # TODO: RuntimeError: Lapack Error in potrf : the leading minor of order 122 is not
            # TODO: positive definite at /pytorch/aten/src/TH/generic/THTensorLapack.c:617
            # feature_gen = self.distribution.sample((batch_size,)).type(torch.float32)
            feature_gen = np.random.multivariate_normal(self.landmarks_mean, self.landmarks_cov, batch_size)
            feature_gen = torch.from_numpy(feature_gen).type(torch.float32)
            feature_gen = (feature_gen - 0.5) * 2.0
            # transfer everything to the gpu
            if self.cuda:
                images, features, z = images.cuda(), features.cuda(), z.cuda()
                feature_gen = feature_gen.cuda()

            ############################
            # (1) Update D network: maximize log(D(x)) + log(1 - D(G(z)))
            ###########################
            if not validate:
                self.D_optimizer.zero_grad()

            # Train on real example with real features
            real_predictions = self.D(images, features)
            d_real_predictions_loss = self.BCE_loss(real_predictions,
                                                    label_real)  # real corresponds to log(D_real)

            if not validate:
                # make backward instantly
                d_real_predictions_loss.backward()

            # Train on real example with fake features
            fake_labels_predictions = self.D(images, feature_gen)
            d_fake_labels_loss = self.BCE_loss(fake_labels_predictions, label_fake) / 2

            if not validate:
                # make backward instantly
                d_fake_labels_loss.backward()

            # Train on fake example from generator
            generated_images = self.G(z, features)
            fake_images_predictions = self.D(generated_images.detach(),
                                             features)  # todo what happens if we detach the output of the Discriminator
            d_fake_images_loss = self.BCE_loss(fake_images_predictions,
                                               label_fake) / 2  # face corresponds to log(1-D_fake)

            if not validate:
                # make backward instantly
                d_fake_images_loss.backward()

            d_loss = d_real_predictions_loss + d_fake_labels_loss + d_fake_images_loss

            if not validate:
                # D_loss.backward()
                self.D_optimizer.step()

            ############################
            # (2) Update G network: maximize log(D(G(z)))
            ###########################
            if not validate:
                self.G_optimizer.zero_grad()

            # Train on fooling the Discriminator
            fake_images_predictions = self.D(generated_images, features)
            g_loss = self.BCE_loss(fake_images_predictions, label_real)

            if not validate:
                g_loss.backward()
                self.G_optimizer.step()

            # losses
            g_loss_summed += g_loss
            d_loss_summed += d_loss
            iterations += 1

        g_loss_summed /= iterations
        d_loss_summed /= iterations

        return g_loss_summed.cpu().data.numpy(), d_loss_summed.cpu().data.numpy(), generated_images

    def train(self, train_data_loader, batch_size, **kwargs):
        g_loss, d_loss, generated_images = self._train(train_data_loader, batch_size, validate=False, **kwargs)
        return g_loss, d_loss, generated_images

    def validate(self, validation_data_loader, batch_size, **kwargs):
        g_loss, d_loss, generated_images = self._train(validation_data_loader, batch_size, validate=True, **kwargs)
        return g_loss, d_loss, generated_images

    def get_models(self):
        return [self.G, self.D]

    def get_model_names(self):
        return ['generator', 'discriminator']

    def get_remaining_modules(self):
        return [self.G_optimizer, self.D_optimizer, self.BCE_loss]

    def log(self, logger, epoch, lossG, lossD, images, log_images=False):  # last parameter is not needed anymore
        """
        use logger to log current loss etc...
        :param logger: logger used to log
        :param epoch: current epoch
        """
        logger.log_loss(epoch=epoch, loss={'lossG': float(lossG), 'lossD': float(lossD)})
        logger.log_fps(epoch=epoch)
        logger.save_model(epoch)

        if log_images:
            self.log_images(logger, epoch, images, validation=False)

    def log_validation(self, logger, epoch, lossG, lossD, images):
        logger.log_loss(epoch=epoch, loss={'lossG_val': float(lossG), 'lossD_val': float(lossD)})

        self.log_images(logger, epoch, images, validation=True)

    def log_images(self, logger, epoch, images, validation=True):
        # images = images.cpu()
        # images *= .5
        # images += .5
        # examples = int(len(images))
        # example_indices = random.sample(range(0, examples - 1), 4 * 4)
        # A = []
        # for idx, i in enumerate(example_indices):
        #     A.append(images[i])
        tag = 'validation_output' if validation else 'training_output'
        logger.log_images(epoch, images, tag, 8)

    def anonymize(self, feature):
        z = torch.randn((feature.shape[0], self.z_dim))
        if self.cuda:
            z, feature = z.cuda(), feature.cuda()
        tensor_img = self.G(z, feature)
        # Denormalize
        for t in tensor_img:  # loop over mini-batch dimension
            norm_img(t)
        tensor_img *= 255
        tensor_img = tensor_img.type(torch.uint8)
        return tensor_img

    def img2latent_bridge(self, extracted_face, extracted_information):
        landmarks = np.array(extracted_information.landmarks) / extracted_information.size_fine
        landmarks = landmarks.reshape(-1)
        # Split x,y coordinate
        landmarks_X, landmarks_Y = landmarks[::2], landmarks[1::2]
        # landmarks_5
        eye_left_X, eye_left_Y = np.mean(landmarks_X[36:42]), np.mean(landmarks_Y[36:42])
        eye_right_X, eye_right_Y = np.mean(landmarks_X[42:48]), np.mean(landmarks_Y[42:48])
        nose_X, nose_Y = np.mean(landmarks_X[31:36]), np.mean(landmarks_Y[31:36])
        mouth_left_X, mouth_left_Y = landmarks_X[48], landmarks_Y[48]
        mouth_right_X, mouth_right_Y = landmarks_X[60], landmarks_Y[60]
        landmarks_5 = np.vstack((eye_left_X, eye_left_Y, eye_right_X, eye_right_Y, nose_X, nose_Y,
                                 mouth_left_X, mouth_left_Y, mouth_right_X, mouth_right_Y)).T
        # Zero centering
        landmarks_5 -= 0.5
        landmarks_5 *= 2.0
        # ToTensor
        feature = torch.from_numpy(landmarks_5).type(torch.float32)

        return feature


def norm_img(img):
    """
    Normalize image via min max inplace
    :param img: Tensor image
    """
    min, max = float(img.min()), float(img.max())
    img.clamp_(min=min, max=max)
    img.add_(-min).div_(max - min + 1e-5)
