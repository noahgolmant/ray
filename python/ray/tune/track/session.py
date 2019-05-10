from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
from datetime import datetime

from ray.tune.trial import Trial
from ray.tune.result import DEFAULT_RESULTS_DIR, TRAINING_ITERATION
from ray.tune.logger import UnifiedLogger, Logger


class _ReporterHook(Logger):
    def __init__(self, tune_reporter):
        self.tune_reporter = tune_reporter

    def on_result(self, metrics):
        return self.tune_reporter(**metrics)


class TrackSession(object):
    """Manages results for a single session.

    Represents a single Trial in an experiment.

    Attributes:
        trial_name (str): Custom trial name.
        experiment_dir (str): Directory where results for all trials
            are stored. Each session is stored into a unique directory
            inside experiment_dir.
        upload_dir (str): Directory to sync results to.
        trial_config (dict): Parameters that will be logged to disk.
        _tune_reporter (StatusReporter): For rerouting when using Tune.
            Will not instantiate logging if not None.
    """

    def __init__(self,
                 trial_name="",
                 experiment_dir=None,
                 upload_dir=None,
                 trial_config=None,
                 _tune_reporter=None):
        self.experiment_dir = None
        self.logdir = None
        self.upload_dir = None
        self.trial_config = None
        self.trial_id = Trial.generate_id()
        if trial_name:
            self.trial_id = trial_name + "_" + self.trial_id
        if _tune_reporter:
            self._logger = _ReporterHook(_tune_reporter)
        else:
            self._initialize_logging(trial_name, experiment_dir, upload_dir,
                                     trial_config)

    def _initialize_logging(self,
                            trial_name="",
                            experiment_dir=None,
                            upload_dir=None,
                            trial_config=None):

        # TODO(rliaw): In other parts of the code, this is `local_dir`.
        if experiment_dir is None:
            experiment_dir = os.path.join(DEFAULT_RESULTS_DIR, "default")

        self.experiment_dir = os.path.expanduser(experiment_dir)

        # TODO(rliaw): Refactor `logdir` to `trial_dir`.
        self.logdir = Trial.generate_logdir(trial_name, self.experiment_dir)
        self.upload_dir = upload_dir
        self.iteration = -1
        self.trial_config = trial_config or {}

        # misc metadata to save as well
        self.trial_config["trial_id"] = self.trial_id
        self._logger = UnifiedLogger(self.trial_config, self.logdir,
                                     self.upload_dir)

    def metric(self, iteration=None, **metrics):
        """Logs all named arguments specified in **metrics.

        This will log trial metrics locally, and they will be synchronized
        with the driver periodically through ray.

        Arguments:
            iteration (int): current iteration of the trial.
            **metrics: named arguments with corresponding values to log.
        """

        # TODO: Implement a batching mechanism for multiple calls to `metric`
        #     within the same iteration.
        metrics_dict = metrics.copy()
        metrics_dict.update({"trial_id": self.trial_id})

        if iteration is not None:
            self.iteration = max(iteration, self.iteration)

        # TODO: Move Trainable autopopulation to a util function
        metrics_dict[TRAINING_ITERATION] = self.iteration
        self._logger.on_result(metrics_dict)

    def close(self):
        self.trial_config["trial_completed"] = True
        self.trial_config["end_time"] = datetime.now().isoformat()
        # TODO(rliaw): Have Tune support updated configs
        self._logger.update_config(self.trial_config)
        self._logger.close()
