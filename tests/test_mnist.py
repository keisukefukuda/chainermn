# coding: utf-8

import sys
import unittest

import chainer
import chainer.functions as F
import chainer.links as L
import chainer.testing
import chainer.testing.attr
from chainer import training
from chainer.training import extensions

import chainermn

import inspect


class MLP(chainer.Chain):
    def __init__(self, n_units, n_out):
        super(MLP, self).__init__(
            l1=L.Linear(784, n_units),
            l2=L.Linear(n_units, n_units),
            l3=L.Linear(n_units, n_out),
        )

    def __call__(self, x):
        h1 = F.relu(self.l1(x))
        h2 = F.relu(self.l2(h1))
        return self.l3(h2)


def location(depth=0):
    frame = inspect.stack()[depth + 1]
    return (frame[1], frame[2])


@chainer.testing.parameterize(
    {'gpu': True},
    {'gpu': False},
)
class TestMNIST(unittest.TestCase):
    def test_mnist(self, display_log=True):
        epoch = 3
        batchsize = 100
        n_units = 100

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()

        if self.gpu:
            comm = chainermn.create_communicator('hierarchical')
            device = comm.intra_rank
            chainer.cuda.get_device(device).use()
        else:
            comm = chainermn.create_communicator('naive')
            device = -1

        model = L.Classifier(MLP(n_units, 10))
        if self.gpu:
            model.to_gpu()

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        optimizer = chainermn.create_multi_node_optimizer(
            chainer.optimizers.Adam(), comm)
        optimizer.setup(model)

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        if comm.rank == 0:
            train, test = chainer.datasets.get_mnist()
        else:
            train, test = None, None

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        train = chainermn.scatter_dataset(train, comm, shuffle=True)
        test = chainermn.scatter_dataset(test, comm, shuffle=True)

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        train_iter = chainer.iterators.SerialIterator(train, batchsize)
        test_iter = chainer.iterators.SerialIterator(test, batchsize,
                                                     repeat=False,
                                                     shuffle=False)

        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        updater = training.StandardUpdater(
            train_iter,
            optimizer,
            device=device
        )

        trainer = training.Trainer(updater, (epoch, 'epoch'))

        # Wrap standard Chainer evaluators by MultiNodeEvaluator.
        evaluator = extensions.Evaluator(test_iter, model, device=device)
        evaluator = chainermn.create_multi_node_evaluator(evaluator, comm)
        trainer.extend(evaluator)

        # Some display and output extensions are necessary only for one worker.
        # (Otherwise, there would just be repeated outputs.)
        if comm.rank == 0 and display_log:
            trainer.extend(extensions.LogReport(trigger=(1, 'epoch')),
                           trigger=(10, 'iteration'))
            trainer.extend(extensions.PrintReport(['epoch',
                                                   'iteration',
                                                   'main/loss',
                                                   'validation/main/loss',
                                                   'main/accuracy',
                                                   'validation/main/accuracy',
                                                   'elapsed_time'],
                                                  out=sys.stderr),
                           trigger=(10, 'iteration'))
        # print("Debug: {}:{}".format(*location()))
        sys.stdout.flush()
        trainer.run()

        err = evaluator()['validation/main/accuracy']
        self.assertGreaterEqual(err, 0.95)


if __name__ == "__main__":
    # print("Debug: {}:{}".format(*location()))
    sys.stdout.flush()
    TestMNIST().test_mnist(display_log=True)
