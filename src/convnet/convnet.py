#
# project: project 2
# file: convnet.py
# author: MING Yao
#
# TODO: Abstract Layer class


import math
import time
import sys
import numpy as np
import tensorflow as tf
from .sequential_net import Layer, SequentialNet
from .classifier import Classifier
from . import utils
from .utils import get_activation, get_learning_rate, get_optimizer, get_regularizer, get_loss_func, output_shape
from .message_protoc.log_message import create_training_log_message, create_evaluation_log_message, log_beautiful_print

SEED = None
_EVAL_BATCH_SIZE = 100

Float32 = tf.float32
Float64 = tf.float64
Float = Float32
Int32 = tf.int32
Int64 = tf.int64
Int = Int32
global_keys = [tf.GraphKeys.GLOBAL_VARIABLES]
local_keys = [tf.GraphKeys.LOCAL_VARIABLES]
weight_keys = global_keys + [tf.GraphKeys.WEIGHTS]
bias_keys = global_keys + [tf.GraphKeys.BIASES]
l_weight_keys = local_keys + [tf.GraphKeys.WEIGHTS]
l_bias_keys = local_keys + [tf.GraphKeys.BIASES]


class InputLayer(Layer):
    """Input Layer"""

    def __init__(self, dshape):
        """

        :param dshape: shape of input data. [batch_size, size_x, size_y, num_channel]
        """
        super().__init__('input')
        self.dshape = dshape
        # with tf.variable_scope(name, reuse=True) as scope:
        #     self.dshape = tf.constant(dshape, dtype=Int,name="dshape")

    def __call__(self, input, name=''):
        super().__call__(input)
        return input

    def compile(self):
        return

    @property
    def output_shape(self):
        return list(self.dshape[1:])

    @property
    def is_compiled(self):
        """
        No need to compile
        """
        return True
    

class ConvLayer(Layer):
    """Input Layer"""

    def __init__(self, filter_size, out_channels, strides, name_or_scope, padding='SAME', activation='linear', has_bias=True):
        """

        :param filter: of shape [m,n]
        :param out_channels:  output channel number, should be an integer
        :param strides: stride size, of shape [x,y]
        :param padding: 'VALID' or 'SAME'
        """
        super().__init__('conv')
        self._filter_shape = filter_size
        self._out_channels = out_channels
        self.strides = [1] + strides + [1]
        self.padding = padding
        self.activation = get_activation(activation)
        self.has_bias = has_bias
        self.filters = None
        self.bias = None
        self.shape = None
        self.name_or_scope = name_or_scope
        self._is_compiled = False
        self._output_shape = None

    def __call__(self, input, name=''):
        with tf.variable_scope(self.name_or_scope, reuse=True):
            super().__call__(input)
            result = tf.nn.conv2d(input, self.filters, self.strides, self.padding, name='conv'+name)
            if self.has_bias:
                result = result + self.bias
            return self.activation(result, name='activate'+name)

    def compile(self):
        assert self.prev is not None
        input_shape = self.prev.output_shape
        # Compute weight shapes
        in_channels = input_shape[-1]
        out_channels = self._out_channels
        self.shape = self._filter_shape + [in_channels, out_channels]

        # Initialize Variables
        with tf.variable_scope(name_or_scope=self.name_or_scope):
            self.filters = tf.get_variable('filters', shape=self.shape, dtype=Float,
                                           initializer=tf.truncated_normal_initializer( stddev=0.1, dtype=Float),
                                           collections=weight_keys)
            tf.summary.tensor_summary(tf.get_variable_scope().name + '_filters', self.filters)
            if self.has_bias:
                self.bias = tf.get_variable('bias', shape=[out_channels], dtype=Float,
                                            initializer=tf.constant_initializer(0.01, dtype=Float),
                                            collections=bias_keys)
            tf.summary.tensor_summary(tf.get_variable_scope().name + '_bias', self.bias)
        self._is_compiled = True

    @property
    def output_shape(self):
        if self._output_shape is None:
            assert self.prev is not None
            input_shape = self.prev.output_shape
            x, y = output_shape(input_shape, self._filter_shape, self.strides, self.padding)
            self._output_shape = [x, y, self._out_channels]
        return self._output_shape

    @property
    def is_compiled(self):
        return self._is_compiled


class PoolLayer(Layer):
    """Pooling Layer"""
    def __init__(self, typename, filter_shape, strides, name_or_scope, padding='SAME'):
        if typename == 'max':
            super().__init__('max_pool')
            self.pool_func = tf.nn.max_pool
        elif typename == 'avg':
            super().__init__('avg_pool')
            self.pool_func = tf.nn.avg_pool
        self._filter_shape = filter_shape
        self._output_shape = None
        self.strides = [1] + strides + [1]
        self.padding = padding
        self.name_or_scope = name_or_scope

    def __call__(self, input, name=''):
        with tf.variable_scope(self.name_or_scope, reuse=True):
            super().__call__(input)
            return self.pool_func(input, self._filter_shape, self.strides, self.padding, name=self.type+name)

    def compile(self):
        return

    @property
    def output_shape(self):
        if self._output_shape is None:
            assert self.prev is not None
            input_shape = self.prev.output_shape
            x, y = output_shape(input_shape, self._filter_shape, self.strides, self.padding)
            self._output_shape = [x, y, input_shape[-1]]
        return self._output_shape

    @property
    def is_compiled(self):
        return True


class DropoutLayer(Layer):

    def __init__(self, keep_prob, name_or_scope):
        super().__init__('dropout')
        self.name_or_scope = name_or_scope
        with tf.variable_scope(name_or_scope):
            self.keep_prob = tf.constant(keep_prob, dtype=Float, name='keep_prob')
        self._output_shape = None

    def __call__(self, input, name=''):
        with tf.variable_scope(self.name_or_scope, reuse=True):
            super().__call__(input)
            return tf.nn.dropout(input, self.keep_prob, name='dropout'+name)

    def compile(self):
        return

    @property
    def output_shape(self):
        if self._output_shape is None:
            self._output_shape = self.prev.output_shape
        return self._output_shape

    @property
    def is_compiled(self):
        return True


class FlattenLayer(Layer):

    def __init__(self, name_or_scope):
        super(FlattenLayer, self).__init__('flatten')
        self._output_shape = None
        self.name_or_scope = name_or_scope

    def __call__(self, input, name=''):
        with tf.variable_scope(self.name_or_scope, reuse=True):
            super(FlattenLayer, self).__call__(input)
            shape = input.get_shape().as_list()
            shape0 = shape[0] if shape[0] is not None else -1
            return tf.reshape(input, [shape0, shape[1] * shape[2] * shape[3]], name='flatten'+name)

    def compile(self):
        return

    @property
    def output_shape(self):
        if self._output_shape is None:
            input_shape = self.prev.output_shape
            self._output_shape = [input_shape[0]*input_shape[1]*input_shape[2]]
        return self._output_shape

    @property
    def is_compiled(self):
        return True


class FullyConnectedLayer(Layer):

    def __init__(self, out_channels, name_or_scope, activation='linear', has_bias=True):
        super(FullyConnectedLayer, self).__init__('fully_connected')
        self.activation = get_activation(activation)
        self.has_bias = has_bias
        self.name_or_scope = name_or_scope
        # self._output_shape = None
        self.shape = None
        self._out_channels = out_channels
        self._is_compiled = False
        self.weights = None
        self.bias = None

    def __call__(self, input, name=''):
        with tf.variable_scope(name_or_scope=self.name_or_scope, reuse=True):
            super(FullyConnectedLayer, self).__call__(input)
            result = tf.matmul(input, self.weights)
            if self.has_bias:
                result = result + self.bias
            return tf.add(self.activation(result),0,name='activation'+name)

    def compile(self):
        assert self.prev is not None
        input_shape = self.prev.output_shape
        # Compute weight shapes
        in_channels = input_shape[-1]
        out_channels = self._out_channels
        self.shape = [in_channels, out_channels]
        # Initialize Variables
        with tf.variable_scope(name_or_scope=self.name_or_scope):
            self.weights = tf.get_variable('weights', shape=self.shape, dtype=Float,
                                           initializer=tf.truncated_normal_initializer(stddev=0.1, dtype=Float),
                                           collections=weight_keys)
            tf.summary.tensor_summary(tf.get_variable_scope().name + '_weights', self.weights)
            if self.has_bias:
                self.bias = tf.get_variable('bias', shape=[out_channels], dtype=Float,
                                            initializer=tf.constant_initializer(0.01, dtype=Float),
                                            collections=bias_keys)
            tf.summary.tensor_summary(tf.get_variable_scope().name + '_bias', self.bias)
        self._is_compiled = True

    @property
    def output_shape(self):
        return [self._out_channels]

    @property
    def is_compiled(self):
        return self._is_compiled


def error_rate(predictions, labels):
    """Return the error rate based on dense predictions and sparse labels."""
    return 100.0 - (100.0 * np.sum(np.argmax(predictions, 1) == labels) / predictions.shape[0])


class ConvNet(SequentialNet, Classifier):
    """A wrapper class for conv net in tensorflow"""

    def __init__(self, name_or_scope, dtype=Float):
        super(ConvNet, self).__init__(name_or_scope)
        self.dtype = dtype
        # array of layer names
        self.layers = []
        self.sess = tf.Session()
        self.summary = None

        # Data and labels
        self.train_data = None
        self.train_labels = None
        self.test_data = None
        self.test_labels = None

        # placeholders for input
        self.train_data_node = None
        self.train_labels_node = None
        self.eval_data_node = None
        self.eval_labels_node = None

        # important compuation node
        self.logits = None
        self.loss = None
        self.loss_func = None

        # Evaluation node
        self.eval_loss = None
        self.eval_logits = None
        self.eval_prediction = None
        self.acc = None
        self.acc5 = None

        # Optimization node
        self.optimizer_op = None
        self.optimizer = tf.train.MomentumOptimizer
        # Either a scalar (constant) or a Tensor (variable) that holds the learning rate
        self.learning_rate = None
        # A Tensor that tracks global step
        self.global_step = tf.Variable(0, dtype=Int, name='global_step', trainable=False)
        # A Tensor that holds current epoch
        self.batch_size_node = tf.placeholder(dtype=Int, shape=(), name='batch_size')
        self.train_size_node = tf.placeholder(dtype=Int, shape=(), name='train_size')
        self.lr_feed_dict = {}
        self.cur_epoch = tf.Variable(0, dtype=Float, name='cur_epoch', trainable=False)
        self.regularizer = lambda x: 0
        self.regularized_term = None
        self.train_writer = None
        self.test_writer = None

    def push_input_layer(self, dshape=None):
        """
        Push a input layer. should be the first layer to be pushed.
        :param dshape: (batch_size, size_x, size_y, num_channel)
        :return: None
        """
        self.push_back(InputLayer(dshape))

        # creating placeholder
        self.train_data_node = tf.placeholder(self.dtype, dshape)
        self.train_labels_node = tf.placeholder(Int, shape=(dshape[0],))
        self.eval_data_node = tf.placeholder(self.dtype, shape=(None, dshape[1], dshape[2],dshape[3]))
        self.eval_labels_node = tf.placeholder(Int, shape=(None,))

    def push_conv_layer(self, filter_size, out_channels, strides, padding='SAME', activation='linear', has_bias=True):
        """
        Push a convolutional layer at the back of the layer list.
        :param filter_size: should be a (x,y) shaped tuple
        :param out_channels: the depth (number of filter) within the layer
        :param strides: a list of int with size 4 indicating filter strides, e.g., [1,2,2,1]
        :param padding: padding algorithm, could be 'SAME' or 'VALID'
        :param activation: TensorFlow activation type default to 'linear', frequent use include 'relu'
        :param has_bias: default to be True
        :return: None
        """
        layer_name = 'conv' + str(self.size)
        self.layers.append(layer_name)
        self.push_back(ConvLayer(filter_size, out_channels, strides, layer_name, padding, activation, has_bias))

    def push_pool_layer(self, type, kernel_size, strides, padding='SAME'):
        """
        Push a pooling layer at the back of the layer list
        :param type: type of pooling, could be 'max' or 'avg'
        :param kernel_size: a list of int indicating kernel size
        :param strides: a list of int with size 4 indicating filter strides, e.g., [1,2,2,1]
        :param padding: padding algorithm, could be 'SAME' or 'VALID'
        :return: None
        """
        layer_name = type + 'pool' + str(self.size)
        self.layers.append(layer_name)
        self.push_back(PoolLayer(type, kernel_size, strides, layer_name, padding))
        # self.layers.append({'type': type, 'kernel': kernel_size, 'strides': strides, 'padding': padding})

    def push_fully_connected_layer(self, out_channels, activation='linear', has_bias=True):
        """
        Push a fully connected layer at the back
        :param out_channels: the output channels of the layer
        :param activation: TensorFlow activation type, default to 'linear', frequent use include 'relu'
        :param has_bias: indicating whether the layer as bias term
        :return: None
        """
        layer_name = 'fully_connected' + str(self.size)
        self.layers.append(layer_name)
        self.push_back(FullyConnectedLayer(out_channels, layer_name, activation, has_bias))
        # self.layers.append({'type':'fully_connected', 'depth': n_units, 'activation': activation, 'isbias': bias})

    def push_flatten_layer(self):
        """
        Push a flatten layer at the back of the layer list.
        There should be a flatten layer between a convolutional layer and a fully connected layer.
        :return: None
        """
        layer_name = 'flatten' + str(self.size)
        self.layers.append(layer_name)
        self.push_back(FlattenLayer(layer_name))

    def push_dropout_layer(self, keep_prob):
        """
        Push a drop out layer at the back of the layer list.
        This layer would only be called in training mode
        :param keep_prob: keep probability of the drop out operation
        :return: None
        """
        layer_name = 'dropout' + str(self.size)
        self.layers.append(layer_name)
        # self.layers.append({"type":"dropout",'prob':prob})
        self.push_back(DropoutLayer(keep_prob, layer_name))

    def set_regularizer(self, regularizer=None, scale=0):
        """
        Set the loss regularizer. default to have no regularization
        :param regularizer: regularizer method. 'l1' or 'l2', or a list of these method
        :param scale: scale factor of the regularization term
        :return: None
        """
        if scale == 0:
            self.regularizer = lambda x: 0
            return
        self.regularizer = get_regularizer(regularizer, scale)

    def set_loss(self, loss, regularizer=None, scale=0):
        """
        Set the type of loss used in training. See convnet.utils.get_loss_func
        :param loss: a string or callable function.
        :param regularizer: indicating the regularizer type. see convnet.ConvNet.set_regularizer
        :param scale: the scale factor of the regularization term
        :return: None
        """
        self.loss_func = get_loss_func(loss)
        if regularizer is not None:
            self.set_regularizer(regularizer, scale)

    def set_optimizer(self, optimizer='Momentum', **kwargs):
        """
        Set the Optimizer function. See convnet.utils.get_optimizer
        :param optimizer: a string indicating the type of the optimizer
        :param kwargs: optimal args of the optimizer. See TensorFlow API
        :return: None
        """
        assert self.learning_rate is not None and self.learning_rate != 0
        self.optimizer = get_optimizer(optimizer)(self.learning_rate, **kwargs)

    def set_learning_rate(self, learning_rate=0.001, update_func=None, **kwargs):
        """
        Set learning rate adjusting scheme. Wrapped from TF api.
        :param learning_rate: the base learning_rate
        :param update_func: a callable function of form updated_rate = update_func(base_rate, global_step).
        :return: None
        """
        if update_func is None:
            self.learning_rate = learning_rate
        else:
            kwargs['global_step'] = self.global_step * self.batch_size_node
            kwargs['learning_rate'] = learning_rate
            kwargs['decay_steps'] = self.train_size_node
            self.learning_rate = get_learning_rate(update_func, **kwargs)

    def set_data(self, train_data, train_labels, test_data=None, test_labels=None):
        """
        Set the training data and test data
        :param train_data:
        :param train_labels:
        :param test_data:
        :param test_labels:
        :return:
        """
        self.train_data = train_data
        self.train_labels = train_labels
        self.test_data = test_data
        self.test_labels = test_labels

    def _cal_loss(self, data_node, labels_node, train, name):
        # logits: the raw output of the model
        logits = self.model(data_node, train)
        # loss: average loss, computed by specified loss_func
        loss = tf.reduce_mean(self.loss_func(logits, labels_node))
        # add a regularized term, note that it is added after taking mean on loss value
        loss = tf.add(loss, self.regularized_term, name=name)
        return logits, loss

    def compile(self, eval=True, test=False):
        """
        Compile the model. Call before training or evaluating
        :return: None
        """

        with tf.variable_scope(self.name_or_scope):
            super(ConvNet, self).compile()
            # init input node
            self.train_data_node = tf.placeholder(Float, [None] + self.front.output_shape, 'train_data')
            self.train_labels_node = tf.placeholder(Int, [None, ], 'train_labels')
            self.eval_data_node = tf.placeholder(Float, [None] + self.front.output_shape, 'eval_data')
            self.eval_labels_node = tf.placeholder(Int, [None, ], 'eval_labels')

            self.regularized_term = self.regularizer(tf.get_collection(tf.GraphKeys.WEIGHTS))

            # computation node for training ops
            self.logits, self.loss = self._cal_loss(self.train_data_node, self.train_labels_node,
                                                    True, 'regularized_loss')

            tf.summary.scalar('loss', self.loss)
            with tf.name_scope('train'):
            # Setup optimizer ops
                self.optimizer_op = self.optimizer.minimize(self.loss, self.global_step)

            # Computation node for evaluations
            if eval:
                with tf.name_scope('eval'):
                    self.eval_logits, self.eval_loss = self._cal_loss(self.eval_data_node,self.eval_labels_node,
                                                                      False, 'regularized_loss')
                    # prediction
                    self.eval_prediction = tf.nn.softmax(self.eval_logits, name='prediction')
                    # accuracy
                    self.acc = self.top_k_acc(self.eval_prediction, self.eval_labels_node, 1, name='acc')
                    self.acc5 = self.top_k_acc(self.eval_prediction, self.eval_labels_node, 5, name='acc5')

        self.summary = tf.summary.merge_all()

        # check requirements for training
        assert self.train_data is not None
        assert self.train_labels is not None
        if test:
            assert self.test_data is not None
            assert self.test_labels is not None

    def model(self, data, train=False):
        """
        The Model definition. Feed in the data and run it through the network
        :param data: A Tensor that holds the data
        :param train: A Boolean, indicating whether the method is called by a training process or a evaluating process
        :return: A Tensor that holds the output of the model, or `logits`.
        """

        # Note that {strides} is a 4D array whose
        # shape matches the data layout: [image index, y, x, depth].

        if train:
            return self.__call__(data, '_train')
        else:  # In evaluation mode, dropout layer is not called
            cur = self.front
            result = data
            while cur != self.end:
                if cur.type != 'dropout':
                    result = cur(result, '_eval')
                cur = cur.next
            return result

    def feed_dict(self, train=False):
        if train:
            return {self.train}
        else:
            pass

    def _train_one_batch(self, session, feed_dict):
        """
        Train one step using a batch of training data and labels
        :param session: the session to run the training
        :param feed_dict: the feeding dictionary of the data
        :return: None
        """

        if isinstance(self.learning_rate, tf.Tensor):
            lr = session.run(self.learning_rate, self.lr_feed_dict)
            feed_dict.update({self.learning_rate: lr})
        session.run(self.optimizer_op, feed_dict)

    def train(self, batch_size, num_epochs=20, eval_frequency=math.inf):
        """
        Main API for training
        :param batch_size: batch size for mini-batch
        :param num_epochs: total training epochs num
        :param eval_frequency: evaluation frequency, i.e., evaluate per `eval_freq` steps.
            Default as math.inf (No evaluation at all).
        :return: None
        """

        self.train_writer = tf.summary.FileWriter(self.name_or_scope+'/train', self.sess.graph)

        train_size = self.train_labels.shape[0]
        self.lr_feed_dict = {self.train_size_node: train_size, self.batch_size_node: batch_size}

        batch_per_epoch = int(train_size / batch_size)
        total_step = batch_per_epoch * num_epochs
        epoch_time = step_time = start_time = time.time()
        with self.sess as sess:
            # Initialize all global variables
            # By default, trainable weights and biases are in global scope
            sess.run(tf.global_variables_initializer())
            for step in range(int(total_step)+1):
                offset = (step * batch_size) % (train_size - batch_size)
                batch_data = self.train_data[offset:(offset + batch_size), ...]
                batch_labels = self.train_labels[offset:(offset + batch_size)]
                feed_dict = {self.train_data_node: batch_data,
                             self.train_labels_node: batch_labels}
                self._train_one_batch(sess, feed_dict)
                if step % 100 == 0 and step != 0:
                    summary = sess.run(self.summary, feed_dict)
                    self.train_writer.add_summary(summary, step)
                    self.train_writer.flush()
                    self.save2file(sess, step)
                    cur_epoch = int(step / batch_per_epoch)
                    batch = step % batch_per_epoch
                    # msg = create_training_log_message(cur_epoch, batch, batch_per_epoch, local_loss,
                    #                                   lr, time.time()-step_time)
                    step_time = time.time()
                    if step % eval_frequency == 0:
                        loss, acc, acc5 = self.eval(sess, self.test_data, self.test_labels, batch_size)
                        # msg.eval_message = create_evaluation_log_message(loss, acc, acc5,
                        #                                                  time.time()-epoch_time, train_size)
                        epoch_time = time.time()
                    # log_beautiful_print(msg)

                else:
                    local_loss, lr = self._train_one_batch(sess, batch_data, batch_labels)

    def infer_in_batches(self, sess, data, batch_size):
        """
        Get logits and predictions of a dataset by running it in small batches.
        :param sess: the tf.Session() to run the computation
        :param data: data used to infer the logits and predictions
        :param batch_size: size of the batch
        :return: logits and predictions
        """
        size = data.shape[0]

        data_node = self.eval_data_node
        num_label = self.back.output_shape[0]

        predictions = np.ndarray(shape=(size, num_label), dtype=np.float32)
        logits = np.ndarray(shape=(size, num_label), dtype=np.float32)
        for begin in range(0, size, batch_size):
            end = begin + batch_size
            if end > size:
                end = size
            logits[begin:end, :] = sess.run(self.eval_logits, feed_dict={data_node: data[begin:end, ...]})
            predictions[begin:end, :] = sess.run(self.eval_prediction,
                                                 feed_dict={self.eval_logits: logits[begin:end, :]})
        return logits, predictions

    def eval(self, sess, data, labels, batch_size=200):
        """
        The evaluating function that will be called at the training API
        :param sess: the tf.Session() to run the computation
        :param data: data used to evaluate the model
        :param labels: data's corresponding labels used to evaluate the model
        :param batch_size: batch sizze
        :return: loss accuracy and accuracy-5
        """
        logits, predictions = self.infer_in_batches(sess, data, batch_size)
        loss = sess.run(self.eval_loss, {self.eval_logits: logits, self.eval_labels_node: labels})
        acc, acc5 = sess.run([self.acc, self.acc5], {self.eval_prediction: predictions, self.eval_labels_node: labels})
        return loss, acc, acc5

    def save2file(self,sess, step, name=None):
        """
        Save the trained model to disk
        :param sess: the running Session
        :param step: current step
        :param name: name of the model file
        :return: None
        """
        if name is None:
            name = self.name_or_scope + '/model'
        utils.create_filename(name)
        saver = tf.train.Saver()
        saver.save(sess, name, global_step=step)

    def load(self, filename):
        pass