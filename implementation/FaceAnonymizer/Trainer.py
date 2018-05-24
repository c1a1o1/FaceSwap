import torch

from Logging.LoggingUtils import Logger
from Configuration.config_general import MOST_RECENT_MODEL
from FaceAnonymizer.DataSplitter import DataSplitter

class Trainer:
    def __init__(self, root_folder, config):
        self.batch_size = config['batch_size']
        self.dataset = config['dataset']
        self.model = config['model']
        self.data_loader = DataSplitter(self.dataset, self.batch_size, config['num_workers'])

        if torch.cuda.device_count() > 1:
            self.batch_size *= torch.cuda.device_count()
            # dataset.size_multiplicator *= torch.cuda.device_count()


        self.logger = Logger(len(self.dataset), self.model, save_model_every_nth=100,
                             shared_model_path=MOST_RECENT_MODEL)
        self.logger.log_config(config)

    def train(self):
        max_epochs = 5000
        validate_every = 20
        for i in range(max_epochs):
            self.model.set_train_mode(True)
            batches = self.data_loader.get_train_data_loader()
            info = self.model.train(i, batches)

            if i % validate_every == 0:
                self.model.log(self.logger, i, *info, log_images=True)
                # do validation
                self.model.set_train_mode(False)
                batches = self.data_loader.get_validation_data_loader()
                info = self.model.validate(batches)
                self.model.log_validate(self.logger, i, *info)
                self.model.set_train_mode(True)
            else:
                self.model.log(self.logger, i, *info)
