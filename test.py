"""
import os
os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
os.environ["PLAIDML_DEVICE_IDS"] = "opencl_nvidia_geforce_gtx_1060_6gb.0"
import keras
KL = keras.layers

x = KL.Input ( (128,128,64) )
label = KL.Input( (1,), dtype="int32")
y = x[:,:,:, label[0,0] ]

import code
code.interact(local=dict(globals(), **locals()))
"""

# import os
# os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
# os.environ["PLAIDML_DEVICE_IDS"] = "opencl_nvidia_geforce_gtx_1060_6gb.0"
# import keras
# K = keras.backend
# import numpy as np

# shape = (64, 64, 3)
# def encflow(x):
#     x = keras.layers.Conv2D(128, 5, strides=2, padding="same")(x)
#     x = keras.layers.Conv2D(256, 5, strides=2, padding="same")(x)
#     x = keras.layers.Dense(3)(keras.layers.Flatten()(x))
#     return x

# def modelify(model_functor):
#     def func(tensor):
#         return keras.models.Model (tensor, model_functor(tensor))
#     return func

# encoder = modelify (encflow)( keras.Input(shape) )

# inp = x = keras.Input(shape)
# code_t = encoder(x)
# loss = K.mean(code_t)

# train_func = K.function ([inp],[loss], keras.optimizers.Adam().get_updates(loss, encoder.trainable_weights) )
# train_func ([ np.zeros ( (1, 64, 64, 3) ) ])

# import code
# code.interact(local=dict(globals(), **locals()))

##########################
"""
import os
os.environ['TF_CUDNN_WORKSPACE_LIMIT_IN_MB'] = '1024'
#os.environ['TF_CUDNN_USE_AUTOTUNE'] = '0'
import numpy as np
import tensorflow as tf
keras = tf.keras
KL = keras.layers
K = keras.backend

bgr_shape = (128, 128, 3)
batch_size = 80#132 #max -tf.1.11.0-cuda 9
#batch_size = 86 #max -tf.1.13.1-cuda 10

class PixelShuffler(keras.layers.Layer):
    def __init__(self, size=(2, 2), data_format=None, **kwargs):
        super(PixelShuffler, self).__init__(**kwargs)
        self.size = size

    def call(self, inputs):

        input_shape = K.int_shape(inputs)
        if len(input_shape) != 4:
            raise ValueError('Inputs should have rank ' +
                             str(4) +
                             '; Received input shape:', str(input_shape))


        batch_size, h, w, c = input_shape
        if batch_size is None:
            batch_size = -1
        rh, rw = self.size
        oh, ow = h * rh, w * rw
        oc = c // (rh * rw)

        out = K.reshape(inputs, (batch_size, h, w, rh, rw, oc))
        out = K.permute_dimensions(out, (0, 1, 3, 2, 4, 5))
        out = K.reshape(out, (batch_size, oh, ow, oc))
        return out

    def compute_output_shape(self, input_shape):

        if len(input_shape) != 4:
            raise ValueError('Inputs should have rank ' +
                             str(4) +
                             '; Received input shape:', str(input_shape))


        height = input_shape[1] * self.size[0] if input_shape[1] is not None else None
        width = input_shape[2] * self.size[1] if input_shape[2] is not None else None
        channels = input_shape[3] // self.size[0] // self.size[1]

        if channels * self.size[0] * self.size[1] != input_shape[3]:
            raise ValueError('channels of input and size are incompatible')

        return (input_shape[0],
                height,
                width,
                channels)

    def get_config(self):
        config = {'size': self.size}
        base_config = super(PixelShuffler, self).get_config()

        return dict(list(base_config.items()) + list(config.items()))

def upscale (dim):
    def func(x):
        return PixelShuffler()((KL.Conv2D(dim * 4, kernel_size=3, strides=1, padding='same')(x)))
    return func

inp = KL.Input(bgr_shape)
x = inp
x = KL.Conv2D(128, 5, strides=2, padding='same')(x)
x = KL.Conv2D(256, 5, strides=2, padding='same')(x)
x = KL.Conv2D(512, 5, strides=2, padding='same')(x)
x = KL.Conv2D(1024, 5, strides=2, padding='same')(x)
x = KL.Dense(1024)(KL.Flatten()(x))
x = KL.Dense(8 * 8 * 1024)(x)
x = KL.Reshape((8, 8, 1024))(x)
x = upscale(512)(x)
x = upscale(256)(x)
x = upscale(128)(x)
x = upscale(64)(x)
x = KL.Conv2D(3, 5, strides=1, padding='same')(x)

model = keras.models.Model ([inp], [x])
model.compile(optimizer=keras.optimizers.Adam(lr=5e-5, beta_1=0.5, beta_2=0.999), loss='mae')

training_data = np.zeros ( (batch_size,128,128,3) )
loss = model.train_on_batch( [training_data], [training_data] )
print ("FINE")

import sys
sys.exit()
"""



import os
#os.environ["DFL_PLAIDML_BUILD"] = "1"
import pickle
import math
import sys
import argparse
from core import pathex
from core import osex
from facelib import LandmarksProcessor
from facelib import FaceType
from pathlib import Path
import numpy as np
from numpy import linalg as npla
import cv2
import time
import multiprocessing
import threading
import traceback
from tqdm import tqdm
from DFLIMG import *
from core.cv2ex import *
import shutil
from core import imagelib
from core.interact import interact as io



def umeyama(src, dst, estimate_scale):
    """Estimate N-D similarity transformation with or without scaling.
    Parameters
    ----------
    src : (M, N) array
        Source coordinates.
    dst : (M, N) array
        Destination coordinates.
    estimate_scale : bool
        Whether to estimate scaling factor.
    Returns
    -------
    T : (N + 1, N + 1)
        The homogeneous similarity transformation matrix. The matrix contains
        NaN values only if the problem is not well-conditioned.
    References
    ----------
    .. [1] "Least-squares estimation of transformation parameters between two
            point patterns", Shinji Umeyama, PAMI 1991, DOI: 10.1109/34.88573
    """

    num = src.shape[0]
    dim = src.shape[1]

    # Compute mean of src and dst.
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)

    # Subtract mean from src and dst.
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    # Eq. (38).
    A = np.dot(dst_demean.T, src_demean) / num

    # Eq. (39).
    d = np.ones((dim,), dtype=np.double)
    if np.linalg.det(A) < 0:
        d[dim - 1] = -1

    T = np.eye(dim + 1, dtype=np.double)

    U, S, V = np.linalg.svd(A)

    # Eq. (40) and (43).
    rank = np.linalg.matrix_rank(A)
    if rank == 0:
        return np.nan * T
    elif rank == dim - 1:
        if np.linalg.det(U) * np.linalg.det(V) > 0:
            T[:dim, :dim] = np.dot(U, V)
        else:
            s = d[dim - 1]
            d[dim - 1] = -1
            T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V))
            d[dim - 1] = s
    else:
        T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V.T))

    if estimate_scale:
        # Eq. (41) and (42).
        scale = 1.0 / src_demean.var(axis=0).sum() * np.dot(S, d)
    else:
        scale = 1.0

    T[:dim, dim] = dst_mean - scale * np.dot(T[:dim, :dim], src_mean.T)
    T[:dim, :dim] *= scale

    return T

def random_transform(image, rotation_range=10, zoom_range=0.5, shift_range=0.05, random_flip=0):
    h, w = image.shape[0:2]
    rotation = np.random.uniform(-rotation_range, rotation_range)
    scale = np.random.uniform(1 - zoom_range, 1 + zoom_range)
    tx = np.random.uniform(-shift_range, shift_range) * w
    ty = np.random.uniform(-shift_range, shift_range) * h
    mat = cv2.getRotationMatrix2D((w // 2, h // 2), rotation, scale)
    mat[:, 2] += (tx, ty)
    result = cv2.warpAffine(
        image, mat, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if np.random.random() < random_flip:
        result = result[:, ::-1]
    return result

# get pair of random warped images from aligned face image
def random_warp(image, coverage=160, scale = 5, zoom = 1):
    assert image.shape == (256, 256, 3)
    range_ = np.linspace(128 - coverage//2, 128 + coverage//2, 5)
    mapx = np.broadcast_to(range_, (5, 5))
    mapy = mapx.T

    mapx = mapx + np.random.normal(size=(5,5), scale=scale)
    mapy = mapy + np.random.normal(size=(5,5), scale=scale)

    interp_mapx = cv2.resize(mapx, (80*zoom,80*zoom))[8*zoom:72*zoom,8*zoom:72*zoom].astype('float32')
    interp_mapy = cv2.resize(mapy, (80*zoom,80*zoom))[8*zoom:72*zoom,8*zoom:72*zoom].astype('float32')

    warped_image = cv2.remap(image, interp_mapx, interp_mapy, cv2.INTER_LINEAR)

    src_points = np.stack([mapx.ravel(), mapy.ravel() ], axis=-1)
    dst_points = np.mgrid[0:65*zoom:16*zoom,0:65*zoom:16*zoom].T.reshape(-1,2)
    mat = umeyama(src_points, dst_points, True)[0:2]

    target_image = cv2.warpAffine(image, mat, (64*zoom,64*zoom))

    return warped_image, target_image

def input_process(stdin_fd, sq, str):
    sys.stdin = os.fdopen(stdin_fd)
    try:
        inp = input (str)
        sq.put (True)
    except:
        sq.put (False)

def input_in_time (str, max_time_sec):
    sq = multiprocessing.Queue()
    p = multiprocessing.Process(target=input_process, args=( sys.stdin.fileno(), sq, str))
    p.start()
    t = time.time()
    inp = False
    while True:
        if not sq.empty():
            inp = sq.get()
            break
        if time.time() - t > max_time_sec:
            break
    p.terminate()
    sys.stdin = os.fdopen( sys.stdin.fileno() )
    return inp



def subprocess(sq,cq):
    prefetch = 2
    while True:
        while prefetch > -1:
            cq.put ( np.array([1]) ) #memory leak numpy==1.16.0 , but all fine in 1.15.4
            #cq.put ( [1] )  #no memory leak
            prefetch -= 1

        sq.get() #waiting msg from serv to continue posting
        prefetch += 1



def get_image_hull_mask (image_shape, image_landmarks):
    if len(image_landmarks) != 68:
        raise Exception('get_image_hull_mask works only with 68 landmarks')

    hull_mask = np.zeros(image_shape[0:2]+(1,),dtype=np.float32)

    cv2.fillConvexPoly( hull_mask, cv2.convexHull( np.concatenate ( (image_landmarks[0:17], image_landmarks[48:], [image_landmarks[0]], [image_landmarks[8]], [image_landmarks[16]]))    ), (1,) )
    cv2.fillConvexPoly( hull_mask, cv2.convexHull( np.concatenate ( (image_landmarks[27:31], [image_landmarks[33]]) )                                                                    ), (1,) )
    cv2.fillConvexPoly( hull_mask, cv2.convexHull( np.concatenate ( (image_landmarks[17:27], [image_landmarks[0]], [image_landmarks[27]], [image_landmarks[16]], [image_landmarks[33]])) ), (1,) )

    return hull_mask


def umeyama(src, dst, estimate_scale):
    """Estimate N-D similarity transformation with or without scaling.
    Parameters
    ----------
    src : (M, N) array
        Source coordinates.
    dst : (M, N) array
        Destination coordinates.
    estimate_scale : bool
        Whether to estimate scaling factor.
    Returns
    -------
    T : (N + 1, N + 1)
        The homogeneous similarity transformation matrix. The matrix contains
        NaN values only if the problem is not well-conditioned.
    References
    ----------
    .. [1] "Least-squares estimation of transformation parameters between two
            point patterns", Shinji Umeyama, PAMI 1991, DOI: 10.1109/34.88573
    """

    num = src.shape[0]
    dim = src.shape[1]

    # Compute mean of src and dst.
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)

    # Subtract mean from src and dst.
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    # Eq. (38).
    A = np.dot(dst_demean.T, src_demean) / num

    # Eq. (39).
    d = np.ones((dim,), dtype=np.double)
    if np.linalg.det(A) < 0:
        d[dim - 1] = -1

    T = np.eye(dim + 1, dtype=np.double)

    U, S, V = np.linalg.svd(A)

    # Eq. (40) and (43).
    rank = np.linalg.matrix_rank(A)
    if rank == 0:
        return np.nan * T
    elif rank == dim - 1:
        if np.linalg.det(U) * np.linalg.det(V) > 0:
            T[:dim, :dim] = np.dot(U, V)
        else:
            s = d[dim - 1]
            d[dim - 1] = -1
            T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V))
            d[dim - 1] = s
    else:
        T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V.T))

    if estimate_scale:
        # Eq. (41) and (42).
        scale = 1.0 / src_demean.var(axis=0).sum() * np.dot(S, d)
    else:
        scale = 1.0

    T[:dim, dim] = dst_mean - scale * np.dot(T[:dim, :dim], src_mean.T)
    T[:dim, :dim] *= scale

    return T

#mean_face_x = np.array([
#0.000213256, 0.0752622, 0.18113, 0.29077, 0.393397, 0.586856, 0.689483, 0.799124,
#0.904991, 0.98004, 0.490127, 0.490127, 0.490127, 0.490127, 0.36688, 0.426036,
#0.490127, 0.554217, 0.613373, 0.121737, 0.187122, 0.265825, 0.334606, 0.260918,
#0.182743, 0.645647, 0.714428, 0.793132, 0.858516, 0.79751, 0.719335, 0.254149,
#0.340985, 0.428858, 0.490127, 0.551395, 0.639268, 0.726104, 0.642159, 0.556721,
#0.490127, 0.423532, 0.338094, 0.290379, 0.428096, 0.490127, 0.552157, 0.689874,
#0.553364, 0.490127, 0.42689 ])
#
#mean_face_y = np.array([
#0.106454, 0.038915, 0.0187482, 0.0344891, 0.0773906, 0.0773906, 0.0344891,
#0.0187482, 0.038915, 0.106454, 0.203352, 0.307009, 0.409805, 0.515625, 0.587326,
#0.609345, 0.628106, 0.609345, 0.587326, 0.216423, 0.178758, 0.179852, 0.231733,
#0.245099, 0.244077, 0.231733, 0.179852, 0.178758, 0.216423, 0.244077, 0.245099,
#0.780233, 0.745405, 0.727388, 0.742578, 0.727388, 0.745405, 0.780233, 0.864805,
#0.902192, 0.909281, 0.902192, 0.864805, 0.784792, 0.778746, 0.785343, 0.778746,
#0.784792, 0.824182, 0.831803, 0.824182 ])
#
#landmarks_2D = np.stack( [ mean_face_x, mean_face_y ], axis=1 )


#alignments = []
#
#aligned_path_image_paths = pathex.get_image_paths("D:\\DeepFaceLab\\workspace issue\\data_dst\\aligned")
#for filepath in tqdm(aligned_path_image_paths, desc="Collecting alignments", ascii=True ):
#    filepath = Path(filepath)
#
#    if filepath.suffix == '.png':
#        dflimg = DFLPNG.load( str(filepath), print_on_no_embedded_data=True )
#    elif filepath.suffix == '.jpg':
#        dflimg = DFLJPG.load ( str(filepath), print_on_no_embedded_data=True )
#    else:
#        print ("%s is not a dfl image file" % (filepath.name) )
#
#    #source_filename_stem = Path( dflimg.get_source_filename() ).stem
#    #if source_filename_stem not in alignments.keys():
#    #    alignments[ source_filename_stem ] = []
#
#    #alignments[ source_filename_stem ].append (dflimg.get_source_landmarks())
#    alignments.append (dflimg.get_source_landmarks())
import string

def tdict2kw_conv2d ( w, b=None ):
    if b is not None:
        return [ np.transpose(w.numpy(), [2,3,1,0]), b.numpy() ]
    else:
        return [ np.transpose(w.numpy(), [2,3,1,0])]

def tdict2kw_depconv2d ( w, b=None ):
    if b is not None:
        return [ np.transpose(w.numpy(), [2,3,0,1]), b.numpy() ]
    else:
        return [ np.transpose(w.numpy(), [2,3,0,1]) ]

def tdict2kw_bn2d( d, name_prefix ):
    return [ d[name_prefix+'.weight'].numpy(),
             d[name_prefix+'.bias'].numpy(),
             d[name_prefix+'.running_mean'].numpy(),
             d[name_prefix+'.running_var'].numpy() ]


def t2kw_conv2d (src):
    if src.bias is not None:
        return [ np.transpose(src.weight.data.cpu().numpy(), [2,3,1,0]), src.bias.data.cpu().numpy() ]
    else:
        return [ np.transpose(src.weight.data.cpu().numpy(), [2,3,1,0])]


def t2kw_bn2d(src):
    return [ src.weight.data.cpu().numpy(), src.bias.data.cpu().numpy(), src.running_mean.cpu().numpy(), src.running_var.cpu().numpy() ]


import scipy as sp

def color_transfer_mkl(x0, x1):
    eps = np.finfo(float).eps

    h,w,c = x0.shape
    h1,w1,c1 = x1.shape

    x0 = x0.reshape ( (h*w,c) )
    x1 = x1.reshape ( (h1*w1,c1) )

    a = np.cov(x0.T)
    b = np.cov(x1.T)

    Da2, Ua = np.linalg.eig(a)
    Da = np.diag(np.sqrt(Da2.clip(eps, None)))

    C = np.dot(np.dot(np.dot(np.dot(Da, Ua.T), b), Ua), Da)

    Dc2, Uc = np.linalg.eig(C)
    Dc = np.diag(np.sqrt(Dc2.clip(eps, None)))

    Da_inv = np.diag(1./(np.diag(Da)))

    t = np.dot(np.dot(np.dot(np.dot(np.dot(np.dot(Ua, Da_inv), Uc), Dc), Uc.T), Da_inv), Ua.T)

    mx0 = np.mean(x0, axis=0)
    mx1 = np.mean(x1, axis=0)

    result = np.dot(x0-mx0, t) + mx1
    return np.clip ( result.reshape ( (h,w,c) ), 0, 1)

def color_transfer_idt(i0, i1, bins=256, n_rot=20):
    relaxation = 1 / n_rot
    h,w,c = i0.shape
    h1,w1,c1 = i1.shape

    i0 = i0.reshape ( (h*w,c) )
    i1 = i1.reshape ( (h1*w1,c1) )

    n_dims = c

    d0 = i0.T
    d1 = i1.T

    for i in range(n_rot):

        r = sp.stats.special_ortho_group.rvs(n_dims).astype(np.float32)

        d0r = np.dot(r, d0)
        d1r = np.dot(r, d1)
        d_r = np.empty_like(d0)

        for j in range(n_dims):

            lo = min(d0r[j].min(), d1r[j].min())
            hi = max(d0r[j].max(), d1r[j].max())

            p0r, edges = np.histogram(d0r[j], bins=bins, range=[lo, hi])
            p1r, _     = np.histogram(d1r[j], bins=bins, range=[lo, hi])

            cp0r = p0r.cumsum().astype(np.float32)
            cp0r /= cp0r[-1]

            cp1r = p1r.cumsum().astype(np.float32)
            cp1r /= cp1r[-1]

            f = np.interp(cp0r, cp1r, edges[1:])

            d_r[j] = np.interp(d0r[j], edges[1:], f, left=0, right=bins)

        d0 = relaxation * np.linalg.solve(r, (d_r - d0r)) + d0

    return np.clip ( d0.T.reshape ( (h,w,c) ), 0, 1)

from core import imagelib


def color_transfer_mix(img_src,img_trg):
    img_src = (img_src*255.0).astype(np.uint8)
    img_trg = (img_trg*255.0).astype(np.uint8)

    img_src_lab = cv2.cvtColor(img_src, cv2.COLOR_BGR2LAB)
    img_trg_lab = cv2.cvtColor(img_trg, cv2.COLOR_BGR2LAB)

    rct_light = np.clip ( imagelib.linear_color_transfer(img_src_lab[...,0:1].astype(np.float32)/255.0,
                                                img_trg_lab[...,0:1].astype(np.float32)/255.0 )[...,0]*255.0,
                          0, 255).astype(np.uint8)

    img_src_lab[...,0] = (np.ones_like (rct_light)*100).astype(np.uint8)
    img_src_lab = cv2.cvtColor(img_src_lab, cv2.COLOR_LAB2BGR)

    img_trg_lab[...,0] = (np.ones_like (rct_light)*100).astype(np.uint8)
    img_trg_lab = cv2.cvtColor(img_trg_lab, cv2.COLOR_LAB2BGR)

    img_rct = imagelib.color_transfer_sot( img_src_lab.astype(np.float32), img_trg_lab.astype(np.float32) )
    img_rct = np.clip(img_rct, 0, 255).astype(np.uint8)

    img_rct = cv2.cvtColor(img_rct, cv2.COLOR_BGR2LAB)
    img_rct[...,0] = rct_light
    img_rct = cv2.cvtColor(img_rct, cv2.COLOR_LAB2BGR)


    return (img_rct / 255.0).astype(np.float32)



def color_transfer_mix2(img_src,img_trg):
    img_src = (img_src*255.0).astype(np.uint8)
    img_trg = (img_trg*255.0).astype(np.uint8)

    img_src_lab = cv2.cvtColor(img_src, cv2.COLOR_BGR2YUV)
    img_trg_lab = cv2.cvtColor(img_trg, cv2.COLOR_BGR2YUV)

    rct_light = np.clip ( imagelib.linear_color_transfer(img_src_lab[...,0:1].astype(np.float32)/255.0,
                                                img_trg_lab[...,0:1].astype(np.float32)/255.0 )[...,0]*255.0,
                          0, 255).astype(np.uint8)

    img_src_lab[...,0] = (np.ones_like (rct_light)*100).astype(np.uint8)
    img_src_lab = cv2.cvtColor(img_src_lab, cv2.COLOR_YUV2BGR)

    img_trg_lab[...,0] = (np.ones_like (rct_light)*100).astype(np.uint8)
    img_trg_lab = cv2.cvtColor(img_trg_lab, cv2.COLOR_YUV2BGR)

    img_rct = imagelib.color_transfer_sot( img_src_lab.astype(np.float32), img_trg_lab.astype(np.float32) )
    img_rct = np.clip(img_rct, 0, 255).astype(np.uint8)

    img_rct = cv2.cvtColor(img_rct, cv2.COLOR_BGR2YUV)
    img_rct[...,0] = rct_light
    img_rct = cv2.cvtColor(img_rct, cv2.COLOR_YUV2BGR)


    return (img_rct / 255.0).astype(np.float32)


def nd_cor(pts1, pts2):
    dtype = pts1.dtype

    for iter in range(10):

        dir = np.random.normal(size=2).astype(dtype)
        dir /= npla.norm(dir)

        proj_pts1 = pts1*dir
        proj_pts2 = pts2*dir
        id_pts1 = np.argsort (proj_pts1)
        id_pts2 = np.argsort (proj_pts2)




def fist(pts_src, pts_dst):

    rot = np.eye (3,3,dtype=np.float32)
    trans = np.zeros (2, dtype=np.float32)
    scaling = 1

    for iter in range(10):

        center1 = np.zeros (2, dtype=np.float32)
        center2 = np.zeros (2, dtype=np.float32)


landmarks_2D = np.array([
[ 0.000213256,  0.106454  ], #17
[ 0.0752622,    0.038915  ], #18
[ 0.18113,      0.0187482 ], #19
[ 0.29077,      0.0344891 ], #20
[ 0.393397,     0.0773906 ], #21
[ 0.586856,     0.0773906 ], #22
[ 0.689483,     0.0344891 ], #23
[ 0.799124,     0.0187482 ], #24
[ 0.904991,     0.038915  ], #25
[ 0.98004,      0.106454  ], #26
[ 0.490127,     0.203352  ], #27
[ 0.490127,     0.307009  ], #28
[ 0.490127,     0.409805  ], #29
[ 0.490127,     0.515625  ], #30
[ 0.36688,      0.587326  ], #31
[ 0.426036,     0.609345  ], #32
[ 0.490127,     0.628106  ], #33
[ 0.554217,     0.609345  ], #34
[ 0.613373,     0.587326  ], #35
[ 0.121737,     0.216423  ], #36
[ 0.187122,     0.178758  ], #37
[ 0.265825,     0.179852  ], #38
[ 0.334606,     0.231733  ], #39
[ 0.260918,     0.245099  ], #40
[ 0.182743,     0.244077  ], #41
[ 0.645647,     0.231733  ], #42
[ 0.714428,     0.179852  ], #43
[ 0.793132,     0.178758  ], #44
[ 0.858516,     0.216423  ], #45
[ 0.79751,      0.244077  ], #46
[ 0.719335,     0.245099  ], #47
[ 0.254149,     0.780233  ], #48
[ 0.340985,     0.745405  ], #49
[ 0.428858,     0.727388  ], #50
[ 0.490127,     0.742578  ], #51
[ 0.551395,     0.727388  ], #52
[ 0.639268,     0.745405  ], #53
[ 0.726104,     0.780233  ], #54
[ 0.642159,     0.864805  ], #55
[ 0.556721,     0.902192  ], #56
[ 0.490127,     0.909281  ], #57
[ 0.423532,     0.902192  ], #58
[ 0.338094,     0.864805  ], #59
[ 0.290379,     0.784792  ], #60
[ 0.428096,     0.778746  ], #61
[ 0.490127,     0.785343  ], #62
[ 0.552157,     0.778746  ], #63
[ 0.689874,     0.784792  ], #64
[ 0.553364,     0.824182  ], #65
[ 0.490127,     0.831803  ], #66
[ 0.42689 ,     0.824182  ]  #67
], dtype=np.float32)


"""

( .Config()
  .sample_host('src_samples', path)

  .index_generator('i1', 'src_samples' )

  .batch(16)
  .warp_params('w1', ...)
  .branch( (.Branch()
            .load_sample('src_samples', 'i1')

           )
         )
)


"""


def _compute_fans(shape, data_format='channels_last'):
    """Computes the number of input and output units for a weight shape.
    # Arguments
        shape: Integer shape tuple.
        data_format: Image data format to use for convolution kernels.
            Note that all kernels in Keras are standardized on the
            `channels_last` ordering (even when inputs are set
            to `channels_first`).
    # Returns
        A tuple of scalars, `(fan_in, fan_out)`.
    # Raises
        ValueError: in case of invalid `data_format` argument.
    """
    if len(shape) == 2:
        fan_in = shape[0]
        fan_out = shape[1]
    elif len(shape) in {3, 4, 5}:
        # Assuming convolution kernels (1D, 2D or 3D).
        # TH kernel shape: (depth, input_depth, ...)
        # TF kernel shape: (..., input_depth, depth)
        if data_format == 'channels_first':
            receptive_field_size = np.prod(shape[2:])
            fan_in = shape[1] * receptive_field_size
            fan_out = shape[0] * receptive_field_size
        elif data_format == 'channels_last':
            receptive_field_size = np.prod(shape[:-2])
            fan_in = shape[-2] * receptive_field_size
            fan_out = shape[-1] * receptive_field_size
        else:
            raise ValueError('Invalid data_format: ' + data_format)
    else:
        # No specific assumptions.
        fan_in = np.sqrt(np.prod(shape))
        fan_out = np.sqrt(np.prod(shape))
    return fan_in, fan_out

def _create_basis(filters, size, floatx, eps_std):
    if size == 1:
        return np.random.normal(0.0, eps_std, (filters, size))

    nbb = filters // size + 1
    li = []
    for i in range(nbb):
        a = np.random.normal(0.0, 1.0, (size, size))
        a = _symmetrize(a)
        u, _, v = np.linalg.svd(a)
        li.extend(u.T.tolist())
    p = np.array(li[:filters], dtype=floatx)
    return p

def _symmetrize(a):
    return a + a.T - np.diag(a.diagonal())

def _scale_filters(filters, variance):
    c_var = np.var(filters)
    p = np.sqrt(variance / c_var)
    return filters * p

def CAGenerateWeights ( shape, floatx, data_format, eps_std=0.05, seed=None ):
    if seed is not None:
        np.random.seed(seed)

    fan_in, fan_out = _compute_fans(shape, data_format)
    variance = 2 / fan_in

    rank = len(shape)
    if rank == 3:
        row, stack_size, filters_size = shape

        transpose_dimensions = (2, 1, 0)
        kernel_shape = (row,)
        correct_ifft = lambda shape, s=[None]: np.fft.irfft(shape, s[0])
        correct_fft = np.fft.rfft

    elif rank == 4:
        row, column, stack_size, filters_size = shape

        transpose_dimensions = (2, 3, 1, 0)
        kernel_shape = (row, column)
        correct_ifft = np.fft.irfft2
        correct_fft = np.fft.rfft2

    elif rank == 5:
        x, y, z, stack_size, filters_size = shape

        transpose_dimensions = (3, 4, 0, 1, 2)
        kernel_shape = (x, y, z)
        correct_fft = np.fft.rfftn
        correct_ifft = np.fft.irfftn
    else:
        raise ValueError('rank unsupported')

    kernel_fourier_shape = correct_fft(np.zeros(kernel_shape)).shape

    init = []
    for i in range(filters_size):
        basis = _create_basis(stack_size, np.prod(kernel_fourier_shape), floatx, eps_std)
        basis = basis.reshape((stack_size,) + kernel_fourier_shape)

        filters = [correct_ifft(x, kernel_shape)
                   + np.random.normal(0, eps_std, kernel_shape)
                   for x in basis]

        init.append(filters)

    # Format of array is now: filters, stack, row, column
    init = np.array(init)
    init = _scale_filters(init, variance)
    return init.transpose(transpose_dimensions)

import scipy
from ctypes import *

from core.joblib import Subprocessor

class CTComputerSubprocessor(Subprocessor):
    class Cli(Subprocessor.Cli):
        def process_data(self, data):
            idx, src_path, dst_path = data
            src_path = Path(src_path)
            dst_path = Path(dst_path)

            src_uint8 = cv2_imread(src_path)
            dst_uint8 = cv2_imread(dst_path)

            src_dflimg = DFLIMG.load(src_path)
            dst_dflimg = DFLIMG.load(dst_path)
            if src_dflimg is None or dst_dflimg is None:
                return idx, [0,0,0,0,0,0]

            src_uint8 = src_uint8*LandmarksProcessor.get_image_hull_mask( src_uint8.shape, src_dflimg.get_landmarks() )
            dst_uint8 = dst_uint8*LandmarksProcessor.get_image_hull_mask( dst_uint8.shape, dst_dflimg.get_landmarks() )

            src = src_uint8.astype(np.float32) / 255.0
            dst = dst_uint8.astype(np.float32) / 255.0

            src_rct = imagelib.reinhard_color_transfer(src_uint8, dst_uint8).astype(np.float32) / 255.0
            src_lct = np.clip( imagelib.linear_color_transfer (src, dst), 0.0, 1.0 )
            src_mkl = imagelib.color_transfer_mkl (src, dst)
            src_idt = imagelib.color_transfer_idt (src, dst)
            src_sot = imagelib.color_transfer_sot (src, dst)

            dst_mean     = np.mean(dst, axis=(0,1) )
            src_mean     = np.mean(src, axis=(0,1) )
            src_rct_mean = np.mean(src_rct, axis=(0,1) )
            src_lct_mean = np.mean(src_lct, axis=(0,1) )
            src_mkl_mean = np.mean(src_mkl, axis=(0,1) )
            src_idt_mean = np.mean(src_idt, axis=(0,1) )
            src_sot_mean = np.mean(src_sot, axis=(0,1) )

            dst_std     = np.sqrt ( np.var(dst, axis=(0,1) ) + 1e-5 )
            src_std     = np.sqrt ( np.var(src, axis=(0,1) ) + 1e-5 )
            src_rct_std = np.sqrt ( np.var(src_rct, axis=(0,1) ) + 1e-5 )
            src_lct_std = np.sqrt ( np.var(src_lct, axis=(0,1) ) + 1e-5 )
            src_mkl_std = np.sqrt ( np.var(src_mkl, axis=(0,1) ) + 1e-5 )
            src_idt_std = np.sqrt ( np.var(src_idt, axis=(0,1) ) + 1e-5 )
            src_sot_std = np.sqrt ( np.var(src_sot, axis=(0,1) ) + 1e-5 )

            def_mean_sum = np.sum( np.square(src_mean-dst_mean) )
            rct_mean_sum = np.sum( np.square(src_rct_mean-dst_mean) )
            lct_mean_sum = np.sum( np.square(src_lct_mean-dst_mean) )
            mkl_mean_sum = np.sum( np.square(src_mkl_mean-dst_mean) )
            idt_mean_sum = np.sum( np.square(src_idt_mean-dst_mean) )
            sot_mean_sum = np.sum( np.square(src_sot_mean-dst_mean) )

            def_std_sum = np.sum( np.square(src_std-dst_std) )
            rct_std_sum = np.sum( np.square(src_rct_std-dst_std) )
            lct_std_sum = np.sum( np.square(src_lct_std-dst_std) )
            mkl_std_sum = np.sum( np.square(src_mkl_std-dst_std) )
            idt_std_sum = np.sum( np.square(src_idt_std-dst_std) )
            sot_std_sum = np.sum( np.square(src_sot_std-dst_std) )

            return idx, [def_mean_sum+def_std_sum,
                            rct_mean_sum+rct_std_sum,
                            lct_mean_sum+lct_std_sum,
                            mkl_mean_sum+mkl_std_sum,
                            idt_mean_sum+idt_std_sum,
                            sot_mean_sum+sot_std_sum
                        ]

    def __init__(self, src_paths, dst_paths ):
        self.src_paths = src_paths
        self.src_paths_idxs = [*range(len(self.src_paths))]
        self.dst_paths = dst_paths
        self.result = [None]*len(self.src_paths)
        super().__init__('CTComputerSubprocessor', CTComputerSubprocessor.Cli, 60)

    def process_info_generator(self):

        for i in range(multiprocessing.cpu_count()):
            yield 'CPU%d' % (i), {}, {}

    def on_clients_initialized(self):
        io.progress_bar ("Computing", len (self.src_paths_idxs))

    def on_clients_finalized(self):
        io.progress_bar_close()

    def get_data(self, host_dict):
        if len (self.src_paths_idxs) > 0:
            idx = self.src_paths_idxs.pop(0)
            src_path = self.src_paths [idx]
            dst_path = self.dst_paths [np.random.randint(len(self.dst_paths))]
            return idx, src_path, dst_path
        return None

    #override
    def on_data_return (self, host_dict, data):
        self.src_paths_idxs.insert(0, data[0])

    #override
    def on_result (self, host_dict, data, result):
        idx, data = result
        self.result[idx] = data
        io.progress_bar_inc(1)

    #override
    def get_result(self):
        return {0:'none',
                1:'rct',
                2:'lct',
                3:'mkl',
                4:'idt',
                5:'sot'
               }[np.argmin(np.mean(np.array(self.result), 0))]

from samplelib import *


#from skimage.transform import rescale

#np.seterr(divide='ignore', invalid='ignore')

def mls_affine_deformation_1pt(p, q, v, alpha=1):
    ''' Calculate the affine deformation of one point.
    This function is used to test the algorithm.
    '''
    ctrls = p.shape[0]
    np.seterr(divide='ignore')
    w = 1.0 / np.sum((p - v) ** 2, axis=1) ** alpha
    w[w == np.inf] = 2**31-1
    pstar = np.sum(p.T * w, axis=1) / np.sum(w)
    qstar = np.sum(q.T * w, axis=1) / np.sum(w)
    phat = p - pstar
    qhat = q - qstar
    reshaped_phat1 = phat.reshape(ctrls, 2, 1)
    reshaped_phat2 = phat.reshape(ctrls, 1, 2)
    reshaped_w = w.reshape(ctrls, 1, 1)
    pTwp = np.sum(reshaped_phat1 * reshaped_w * reshaped_phat2, axis=0)
    try:
        inv_pTwp = np.linalg.inv(pTwp)
    except np.linalg.linalg.LinAlgError:
        if np.linalg.det(pTwp) < 1e-8:
            new_v = v + qstar - pstar
            return new_v
        else:
            raise
    mul_left = v - pstar
    mul_right = np.sum(reshaped_phat1 * reshaped_w * qhat[:, np.newaxis, :], axis=0)
    new_v = np.dot(np.dot(mul_left, inv_pTwp), mul_right) + qstar
    return new_v

def mls_affine_deformation(image, p, q, alpha=1.0, density=1.0):
    ''' Affine deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Precompute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    w[w == np.inf] = 2**31 - 1
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_phat1 = phat.reshape(ctrls, 2, 1, grow, gcol)                              # [ctrls, 2, 1, grow, gcol]
    reshaped_phat2 = phat.reshape(ctrls, 1, 2, grow, gcol)                              # [ctrls, 1, 2, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]
    pTwp = np.sum(reshaped_phat1 * reshaped_w * reshaped_phat2, axis=0)                 # [2, 2, grow, gcol]
    try:
        inv_pTwp = np.linalg.inv(pTwp.transpose(2, 3, 0, 1))                            # [grow, gcol, 2, 2]
        flag = False
    except np.linalg.linalg.LinAlgError:
        flag = True
        det = np.linalg.det(pTwp.transpose(2, 3, 0, 1))                                 # [grow, gcol]
        det[det < 1e-8] = np.inf
        reshaped_det = det.reshape(1, 1, grow, gcol)                                    # [1, 1, grow, gcol]
        adjoint = pTwp[[[1, 0], [1, 0]], [[1, 1], [0, 0]], :, :]                        # [2, 2, grow, gcol]
        adjoint[[0, 1], [1, 0], :, :] = -adjoint[[0, 1], [1, 0], :, :]                  # [2, 2, grow, gcol]
        inv_pTwp = (adjoint / reshaped_det).transpose(2, 3, 0, 1)                       # [grow, gcol, 2, 2]
    mul_left = reshaped_v - pstar                                                       # [2, grow, gcol]
    reshaped_mul_left = mul_left.reshape(1, 2, grow, gcol).transpose(2, 3, 0, 1)        # [grow, gcol, 1, 2]
    mul_right = reshaped_w * reshaped_phat1                                             # [ctrls, 2, 1, grow, gcol]
    reshaped_mul_right =mul_right.transpose(0, 3, 4, 1, 2)                              # [ctrls, grow, gcol, 2, 1]
    A = np.matmul(np.matmul(reshaped_mul_left, inv_pTwp), reshaped_mul_right)           # [ctrls, grow, gcol, 1, 1]
    reshaped_A = A.reshape(ctrls, 1, grow, gcol)                                        # [ctrls, 1, grow, gcol]

    # Calculate q
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [ctrls, 2, grow, gcol]

    # Get final image transfomer -- 3-D array
    transformers = np.sum(reshaped_A * qhat, axis=0) + qstar                            # [2, grow, gcol]

    # Correct the points where pTwp is singular
    if flag:
        blidx = det == np.inf    # bool index
        transformers[0][blidx] = vx[blidx] + qstar[0][blidx] - pstar[0][blidx]
        transformers[1][blidx] = vy[blidx] + qstar[1][blidx] - pstar[1][blidx]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = np.ones_like(image) * 255
    new_gridY, new_gridX = np.meshgrid((np.arange(gcol) / density).astype(np.int16),
                                        (np.arange(grow) / density).astype(np.int16))
    transformed_image[tuple(transformers.astype(np.int16))] = image[new_gridX, new_gridY]    # [grow, gcol]

    return transformed_image

def mls_affine_deformation_inv(image, p, q, alpha=1.0, density=1.0):
    ''' Affine inverse deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Compute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    w[w == np.inf] = 2**31 - 1
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [ctrls, 2, grow, gcol]

    reshaped_phat = phat.reshape(ctrls, 2, 1, grow, gcol)                               # [ctrls, 2, 1, grow, gcol]
    reshaped_phat2 = phat.reshape(ctrls, 1, 2, grow, gcol)                              # [ctrls, 2, 1, grow, gcol]
    reshaped_qhat = qhat.reshape(ctrls, 1, 2, grow, gcol)                               # [ctrls, 1, 2, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]
    pTwq = np.sum(reshaped_phat * reshaped_w * reshaped_qhat, axis=0)                   # [2, 2, grow, gcol]
    try:
        inv_pTwq = np.linalg.inv(pTwq.transpose(2, 3, 0, 1))                            # [grow, gcol, 2, 2]
        flag = False
    except np.linalg.linalg.LinAlgError:
        flag = True
        det = np.linalg.det(pTwq.transpose(2, 3, 0, 1))                                 # [grow, gcol]
        det[det < 1e-8] = np.inf
        reshaped_det = det.reshape(1, 1, grow, gcol)                                    # [1, 1, grow, gcol]
        adjoint = pTwq[[[1, 0], [1, 0]], [[1, 1], [0, 0]], :, :]                        # [2, 2, grow, gcol]
        adjoint[[0, 1], [1, 0], :, :] = -adjoint[[0, 1], [1, 0], :, :]                  # [2, 2, grow, gcol]
        inv_pTwq = (adjoint / reshaped_det).transpose(2, 3, 0, 1)                       # [grow, gcol, 2, 2]
    mul_left = reshaped_v - qstar                                                       # [2, grow, gcol]
    reshaped_mul_left = mul_left.reshape(1, 2, grow, gcol).transpose(2, 3, 0, 1)        # [grow, gcol, 1, 2]
    mul_right = np.sum(reshaped_phat * reshaped_w * reshaped_phat2, axis=0)             # [2, 2, grow, gcol]
    reshaped_mul_right =mul_right.transpose(2, 3, 0, 1)                                 # [grow, gcol, 2, 2]
    temp = np.matmul(np.matmul(reshaped_mul_left, inv_pTwq), reshaped_mul_right)        # [grow, gcol, 1, 2]
    reshaped_temp = temp.reshape(grow, gcol, 2).transpose(2, 0, 1)                      # [2, grow, gcol]

    # Get final image transfomer -- 3-D array
    transformers = reshaped_temp + pstar                                                # [2, grow, gcol]

    # Correct the points where pTwp is singular
    if flag:
        blidx = det == np.inf    # bool index
        transformers[0][blidx] = vx[blidx] + qstar[0][blidx] - pstar[0][blidx]
        transformers[1][blidx] = vy[blidx] + qstar[1][blidx] - pstar[1][blidx]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = image[tuple(transformers.astype(np.int16))]    # [grow, gcol]

    # Rescale image
    transformed_image = rescale(transformed_image, scale=1.0 / density, mode='reflect')

    return transformed_image






def mls_similarity_deformation(image, p, q, alpha=1.0, density=1.0):
    ''' Similarity deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Compute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    sum_w = np.sum(w, axis=0)                                                           # [grow, gcol]
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / sum_w                # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_phat1 = phat.reshape(ctrls, 1, 2, grow, gcol)                              # [ctrls, 1, 2, grow, gcol]
    reshaped_phat2 = phat.reshape(ctrls, 2, 1, grow, gcol)                              # [ctrls, 2, 1, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]
    mu = np.sum(np.matmul(reshaped_w.transpose(0, 3, 4, 1, 2) *
                          reshaped_phat1.transpose(0, 3, 4, 1, 2),
                          reshaped_phat2.transpose(0, 3, 4, 1, 2)), axis=0)             # [grow, gcol, 1, 1]
    reshaped_mu = mu.reshape(1, grow, gcol)                                             # [1, grow, gcol]
    neg_phat_verti = phat[:, [1, 0],...]                                                # [ctrls, 2, grow, gcol]
    neg_phat_verti[:, 1,...] = -neg_phat_verti[:, 1,...]
    reshaped_neg_phat_verti = neg_phat_verti.reshape(ctrls, 1, 2, grow, gcol)           # [ctrls, 1, 2, grow, gcol]
    mul_left = np.concatenate((reshaped_phat1, reshaped_neg_phat_verti), axis=1)        # [ctrls, 2, 2, grow, gcol]
    vpstar = reshaped_v - pstar                                                         # [2, grow, gcol]
    reshaped_vpstar = vpstar.reshape(2, 1, grow, gcol)                                  # [2, 1, grow, gcol]
    neg_vpstar_verti = vpstar[[1, 0],...]                                               # [2, grow, gcol]
    neg_vpstar_verti[1,...] = -neg_vpstar_verti[1,...]
    reshaped_neg_vpstar_verti = neg_vpstar_verti.reshape(2, 1, grow, gcol)              # [2, 1, grow, gcol]
    mul_right = np.concatenate((reshaped_vpstar, reshaped_neg_vpstar_verti), axis=1)    # [2, 2, grow, gcol]
    reshaped_mul_right = mul_right.reshape(1, 2, 2, grow, gcol)                         # [1, 2, 2, grow, gcol]
    A = np.matmul((reshaped_w * mul_left).transpose(0, 3, 4, 1, 2),
                       reshaped_mul_right.transpose(0, 3, 4, 1, 2))                     # [ctrls, grow, gcol, 2, 2]

     # Calculate q
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_qhat = qhat.reshape(ctrls, 1, 2, grow, gcol).transpose(0, 3, 4, 1, 2)      # [ctrls, grow, gcol, 1, 2]

    # Get final image transfomer -- 3-D array
    temp = np.sum(np.matmul(reshaped_qhat, A), axis=0).transpose(2, 3, 0, 1)            # [1, 2, grow, gcol]
    reshaped_temp = temp.reshape(2, grow, gcol)                                         # [2, grow, gcol]
    transformers = reshaped_temp / reshaped_mu  + qstar                                 # [2, grow, gcol]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = np.ones_like(image) * 255
    new_gridY, new_gridX = np.meshgrid((np.arange(gcol) / density).astype(np.int16),
                                        (np.arange(grow) / density).astype(np.int16))
    transformed_image[tuple(transformers.astype(np.int16))] = image[new_gridX, new_gridY]    # [grow, gcol]

    return transformed_image


def mls_similarity_deformation_inv(image, p, q, alpha=1.0, density=1.0):
    ''' Similarity inverse deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Compute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    w[w == np.inf] = 2**31 - 1
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_phat1 = phat.reshape(ctrls, 1, 2, grow, gcol)                              # [ctrls, 1, 2, grow, gcol]
    reshaped_phat2 = phat.reshape(ctrls, 2, 1, grow, gcol)                              # [ctrls, 2, 1, grow, gcol]
    reshaped_qhat = qhat.reshape(ctrls, 1, 2, grow, gcol)                               # [ctrls, 1, 2, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]

    mu = np.sum(np.matmul(reshaped_w.transpose(0, 3, 4, 1, 2) *
                          reshaped_phat1.transpose(0, 3, 4, 1, 2),
                          reshaped_phat2.transpose(0, 3, 4, 1, 2)), axis=0)             # [grow, gcol, 1, 1]
    reshaped_mu = mu.reshape(1, grow, gcol)                                             # [1, grow, gcol]
    neg_phat_verti = phat[:, [1, 0],...]                                                # [ctrls, 2, grow, gcol]
    neg_phat_verti[:, 1,...] = -neg_phat_verti[:, 1,...]
    reshaped_neg_phat_verti = neg_phat_verti.reshape(ctrls, 1, 2, grow, gcol)           # [ctrls, 1, 2, grow, gcol]
    mul_right = np.concatenate((reshaped_phat1, reshaped_neg_phat_verti), axis=1)       # [ctrls, 2, 2, grow, gcol]
    mul_left = reshaped_qhat * reshaped_w                                               # [ctrls, 1, 2, grow, gcol]
    Delta = np.sum(np.matmul(mul_left.transpose(0, 3, 4, 1, 2),
                             mul_right.transpose(0, 3, 4, 1, 2)),
                   axis=0).transpose(0, 1, 3, 2)                                        # [grow, gcol, 2, 1]
    Delta_verti = Delta[...,[1, 0],:]                                                   # [grow, gcol, 2, 1]
    Delta_verti[...,0,:] = -Delta_verti[...,0,:]
    B = np.concatenate((Delta, Delta_verti), axis=3)                                    # [grow, gcol, 2, 2]
    try:
        inv_B = np.linalg.inv(B)                                                        # [grow, gcol, 2, 2]
        flag = False
    except np.linalg.linalg.LinAlgError:
        flag = True
        det = np.linalg.det(B)                                                          # [grow, gcol]
        det[det < 1e-8] = np.inf
        reshaped_det = det.reshape(grow, gcol, 1, 1)                                    # [grow, gcol, 1, 1]
        adjoint = B[:,:,[[1, 0], [1, 0]], [[1, 1], [0, 0]]]                             # [grow, gcol, 2, 2]
        adjoint[:,:,[0, 1], [1, 0]] = -adjoint[:,:,[0, 1], [1, 0]]                      # [grow, gcol, 2, 2]
        inv_B = (adjoint / reshaped_det).transpose(2, 3, 0, 1)                          # [2, 2, grow, gcol]

    v_minus_qstar_mul_mu = (reshaped_v - qstar) * reshaped_mu                           # [2, grow, gcol]

    # Get final image transfomer -- 3-D array
    reshaped_v_minus_qstar_mul_mu = v_minus_qstar_mul_mu.reshape(1, 2, grow, gcol)      # [1, 2, grow, gcol]
    transformers = np.matmul(reshaped_v_minus_qstar_mul_mu.transpose(2, 3, 0, 1),
                            inv_B).reshape(grow, gcol, 2).transpose(2, 0, 1) + pstar    # [2, grow, gcol]

    # Correct the points where pTwp is singular
    if flag:
        blidx = det == np.inf    # bool index
        transformers[0][blidx] = vx[blidx] + qstar[0][blidx] - pstar[0][blidx]
        transformers[1][blidx] = vy[blidx] + qstar[1][blidx] - pstar[1][blidx]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = image[tuple(transformers.astype(np.int16))]    # [grow, gcol]

    # Rescale image
    transformed_image = rescale(transformed_image, scale=1.0 / density, mode='reflect')

    return transformed_image


def mls_rigid_deformation(image, p, q, alpha=1.0, density=1.0):
    ''' Rigid deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Compute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    sum_w = np.sum(w, axis=0)                                                           # [grow, gcol]
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / sum_w                # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_phat = phat.reshape(ctrls, 1, 2, grow, gcol)                               # [ctrls, 1, 2, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]
    neg_phat_verti = phat[:, [1, 0],...]                                                # [ctrls, 2, grow, gcol]
    neg_phat_verti[:, 1,...] = -neg_phat_verti[:, 1,...]
    reshaped_neg_phat_verti = neg_phat_verti.reshape(ctrls, 1, 2, grow, gcol)           # [ctrls, 1, 2, grow, gcol]
    mul_left = np.concatenate((reshaped_phat, reshaped_neg_phat_verti), axis=1)         # [ctrls, 2, 2, grow, gcol]
    vpstar = reshaped_v - pstar                                                         # [2, grow, gcol]
    reshaped_vpstar = vpstar.reshape(2, 1, grow, gcol)                                  # [2, 1, grow, gcol]
    neg_vpstar_verti = vpstar[[1, 0],...]                                               # [2, grow, gcol]
    neg_vpstar_verti[1,...] = -neg_vpstar_verti[1,...]
    reshaped_neg_vpstar_verti = neg_vpstar_verti.reshape(2, 1, grow, gcol)              # [2, 1, grow, gcol]
    mul_right = np.concatenate((reshaped_vpstar, reshaped_neg_vpstar_verti), axis=1)    # [2, 2, grow, gcol]
    reshaped_mul_right = mul_right.reshape(1, 2, 2, grow, gcol)                         # [1, 2, 2, grow, gcol]
    A = np.matmul((reshaped_w * mul_left).transpose(0, 3, 4, 1, 2),
                       reshaped_mul_right.transpose(0, 3, 4, 1, 2))                     # [ctrls, grow, gcol, 2, 2]

    # Calculate q
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [2, grow, gcol]
    reshaped_qhat = qhat.reshape(ctrls, 1, 2, grow, gcol).transpose(0, 3, 4, 1, 2)      # [ctrls, grow, gcol, 1, 2]

    # Get final image transfomer -- 3-D array
    temp = np.sum(np.matmul(reshaped_qhat, A), axis=0).transpose(2, 3, 0, 1)            # [1, 2, grow, gcol]
    reshaped_temp = temp.reshape(2, grow, gcol)                                         # [2, grow, gcol]
    norm_reshaped_temp = np.linalg.norm(reshaped_temp, axis=0, keepdims=True)           # [1, grow, gcol]
    norm_vpstar = np.linalg.norm(vpstar, axis=0, keepdims=True)                         # [1, grow, gcol]
    transformers = reshaped_temp / norm_reshaped_temp * norm_vpstar  + qstar            # [2, grow, gcol]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = np.ones_like(image) * 255
    new_gridY, new_gridX = np.meshgrid((np.arange(gcol) / density).astype(np.int16),
                                        (np.arange(grow) / density).astype(np.int16))
    transformed_image[tuple(transformers.astype(np.int16))] = image[new_gridX, new_gridY]    # [grow, gcol]

    return transformed_image

def mls_rigid_deformation_inv(image, p, q, alpha=1.0, density=1.0):
    ''' Rigid inverse deformation
    ### Params:
        * image - ndarray: original image
        * p - ndarray: an array with size [n, 2], original control points
        * q - ndarray: an array with size [n, 2], final control points
        * alpha - float: parameter used by weights
        * density - float: density of the grids
    ### Return:
        A deformed image.
    '''
    height = image.shape[0]
    width = image.shape[1]
    # Change (x, y) to (row, col)
    q = q[:, [1, 0]]
    p = p[:, [1, 0]]

    # Make grids on the original image
    gridX = np.linspace(0, width, num=int(width*density), endpoint=False)
    gridY = np.linspace(0, height, num=int(height*density), endpoint=False)
    vy, vx = np.meshgrid(gridX, gridY)
    grow = vx.shape[0]  # grid rows
    gcol = vx.shape[1]  # grid cols
    ctrls = p.shape[0]  # control points

    # Compute
    reshaped_p = p.reshape(ctrls, 2, 1, 1)                                              # [ctrls, 2, 1, 1]
    reshaped_q = q.reshape((ctrls, 2, 1, 1))                                            # [ctrls, 2, 1, 1]
    reshaped_v = np.vstack((vx.reshape(1, grow, gcol), vy.reshape(1, grow, gcol)))      # [2, grow, gcol]

    w = 1.0 / np.sum((reshaped_p - reshaped_v) ** 2, axis=1)**alpha                     # [ctrls, grow, gcol]
    w[w == np.inf] = 2**31 - 1
    pstar = np.sum(w * reshaped_p.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    phat = reshaped_p - pstar                                                           # [ctrls, 2, grow, gcol]
    qstar = np.sum(w * reshaped_q.transpose(1, 0, 2, 3), axis=1) / np.sum(w, axis=0)    # [2, grow, gcol]
    qhat = reshaped_q - qstar                                                           # [ctrls, 2, grow, gcol]
    reshaped_phat1 = phat.reshape(ctrls, 1, 2, grow, gcol)                              # [ctrls, 1, 2, grow, gcol]
    reshaped_phat2 = phat.reshape(ctrls, 2, 1, grow, gcol)                              # [ctrls, 2, 1, grow, gcol]
    reshaped_qhat = qhat.reshape(ctrls, 1, 2, grow, gcol)                               # [ctrls, 1, 2, grow, gcol]
    reshaped_w = w.reshape(ctrls, 1, 1, grow, gcol)                                     # [ctrls, 1, 1, grow, gcol]

    mu = np.sum(np.matmul(reshaped_w.transpose(0, 3, 4, 1, 2) *
                          reshaped_phat1.transpose(0, 3, 4, 1, 2),
                          reshaped_phat2.transpose(0, 3, 4, 1, 2)), axis=0)             # [grow, gcol, 1, 1]
    reshaped_mu = mu.reshape(1, grow, gcol)                                             # [1, grow, gcol]
    neg_phat_verti = phat[:, [1, 0],...]                                                # [ctrls, 2, grow, gcol]
    neg_phat_verti[:, 1,...] = -neg_phat_verti[:, 1,...]
    reshaped_neg_phat_verti = neg_phat_verti.reshape(ctrls, 1, 2, grow, gcol)           # [ctrls, 1, 2, grow, gcol]
    mul_right = np.concatenate((reshaped_phat1, reshaped_neg_phat_verti), axis=1)       # [ctrls, 2, 2, grow, gcol]
    mul_left = reshaped_qhat * reshaped_w                                               # [ctrls, 1, 2, grow, gcol]
    Delta = np.sum(np.matmul(mul_left.transpose(0, 3, 4, 1, 2),
                             mul_right.transpose(0, 3, 4, 1, 2)),
                   axis=0).transpose(0, 1, 3, 2)                                        # [grow, gcol, 2, 1]
    Delta_verti = Delta[...,[1, 0],:]                                                   # [grow, gcol, 2, 1]
    Delta_verti[...,0,:] = -Delta_verti[...,0,:]
    B = np.concatenate((Delta, Delta_verti), axis=3)                                    # [grow, gcol, 2, 2]
    try:
        inv_B = np.linalg.inv(B)                                                        # [grow, gcol, 2, 2]
        flag = False
    except np.linalg.linalg.LinAlgError:
        flag = True
        det = np.linalg.det(B)                                                          # [grow, gcol]
        det[det < 1e-8] = np.inf
        reshaped_det = det.reshape(grow, gcol, 1, 1)                                    # [grow, gcol, 1, 1]
        adjoint = B[:,:,[[1, 0], [1, 0]], [[1, 1], [0, 0]]]                             # [grow, gcol, 2, 2]
        adjoint[:,:,[0, 1], [1, 0]] = -adjoint[:,:,[0, 1], [1, 0]]                      # [grow, gcol, 2, 2]
        inv_B = (adjoint / reshaped_det).transpose(2, 3, 0, 1)                          # [2, 2, grow, gcol]

    vqstar = reshaped_v - qstar                                                         # [2, grow, gcol]
    reshaped_vqstar = vqstar.reshape(1, 2, grow, gcol)                                  # [1, 2, grow, gcol]

    # Get final image transfomer -- 3-D array
    temp = np.matmul(reshaped_vqstar.transpose(2, 3, 0, 1),
                     inv_B).reshape(grow, gcol, 2).transpose(2, 0, 1)                   # [2, grow, gcol]
    norm_temp = np.linalg.norm(temp, axis=0, keepdims=True)                             # [1, grow, gcol]
    norm_vqstar = np.linalg.norm(vqstar, axis=0, keepdims=True)                         # [1, grow, gcol]
    transformers = temp / norm_temp * norm_vqstar + pstar                               # [2, grow, gcol]

    # Correct the points where pTwp is singular
    if flag:
        blidx = det == np.inf    # bool index
        transformers[0][blidx] = vx[blidx] + qstar[0][blidx] - pstar[0][blidx]
        transformers[1][blidx] = vy[blidx] + qstar[1][blidx] - pstar[1][blidx]

    # Removed the points outside the border
    transformers[transformers < 0] = 0
    transformers[0][transformers[0] > height - 1] = 0
    transformers[1][transformers[1] > width - 1] = 0

    # Mapping original image
    transformed_image = image[tuple(transformers.astype(np.int16))]    # [grow, gcol]

    # Rescale image
    transformed_image = rescale(transformed_image, scale=1.0 / density, mode='reflect')

    return transformed_image

def color_transfer_sot(src,trg, steps=10, batch_size=5, reg_sigmaXY=16.0, reg_sigmaV=5.0):
    """
    Color Transform via Sliced Optimal Transfer
    ported by @iperov from https://github.com/dcoeurjo/OTColorTransfer

    src         - any float range any channel image
    dst         - any float range any channel image, same shape as src
    steps       - number of solver steps
    batch_size  - solver batch size
    reg_sigmaXY - apply regularization and sigmaXY of filter, otherwise set to 0.0
    reg_sigmaV  - sigmaV of filter

    return value - clip it manually
    """
    if not np.issubdtype(src.dtype, np.floating):
        raise ValueError("src value must be float")
    if not np.issubdtype(trg.dtype, np.floating):
        raise ValueError("trg value must be float")

    if len(src.shape) != 3:
        raise ValueError("src shape must have rank 3 (h,w,c)")

    if src.shape != trg.shape:
        raise ValueError("src and trg shapes must be equal")

    h,w,c = src.shape
    src_orig = src
    src_dtype = src.dtype

    trg =        trg.reshape( (1, h*w, c) )
    src = src.copy().reshape( (1, h*w, c) )

    idx_offsets = np.tile( np.array( [[h*w]]), (batch_size, 1) )*np.arange(0,batch_size)[:,None]

    for step in range (steps):
        dir = np.random.normal( size=(batch_size,c) ).astype(src_dtype)
        dir /= npla.norm(dir, axis=1, keepdims=True)


        projsource = np.sum( src * dir[:,None,:], axis=-1 )
        projtarget = np.sum( trg * dir[:,None,:], axis=-1 )

        idSource = np.argsort (projsource) + idx_offsets
        idTarget = np.argsort (projtarget) + idx_offsets

        x = projtarget.reshape ( (batch_size*h*w) )[idTarget] - \
            projsource.reshape ( (batch_size*h*w) )[idSource]

        q = x[:,:,None] * dir[:,None,:]
        src += np.mean( x[:,:,None] * dir[:,None,:], axis=0, keepdims=True )

        import code
        code.interact(local=dict(globals(), **locals()))

    src = src.reshape( src_orig.shape )

    if reg_sigmaXY != 0.0:
        src_diff = src-src_orig
        src_diff_filt = cv2.bilateralFilter (src_diff, 0, reg_sigmaV, reg_sigmaXY )
        if len(src_diff_filt.shape) == 2:
            src_diff_filt = src_diff_filt[...,None]
        src = src + src_diff_filt
    return src

import cv2
import scipy
import trimesh
import numpy as np
from scipy.spatial import ConvexHull
from cv2.ximgproc import createGuidedFilter

# Some image resizing tricks.
def min_resize(x, m):
    if x.shape[0] < x.shape[1]:
        s0 = m
        s1 = int(float(m) / float(x.shape[0]) * float(x.shape[1]))
    else:
        s0 = int(float(m) / float(x.shape[1]) * float(x.shape[0]))
        s1 = m
    new_max = min(s1, s0)
    raw_max = min(x.shape[0], x.shape[1])
    if new_max < raw_max:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_LANCZOS4
    y = cv2.resize(x, (s1, s0), interpolation=interpolation)
    return y


# Some image resizing tricks.
def d_resize(x, d, fac=1.0):
    new_min = min(int(d[1] * fac), int(d[0] * fac))
    raw_min = min(x.shape[0], x.shape[1])
    if new_min < raw_min:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_LANCZOS4
    y = cv2.resize(x, (int(d[1] * fac), int(d[0] * fac)), interpolation=interpolation)
    return y


# Some image gradient computing tricks.
def get_image_gradient(dist):
    cols = cv2.filter2D(dist, cv2.CV_32F, np.array([[-1, 0, +1], [-2, 0, +2], [-1, 0, +1]]))
    rows = cv2.filter2D(dist, cv2.CV_32F, np.array([[-1, -2, -1], [0, 0, 0], [+1, +2, +1]]))
    return cols, rows


def generate_lighting_effects(stroke_density, content):

    # Computing the coarse lighting effects
    # In original paper we compute the coarse effects using Gaussian filters.
    # Here we use a Gaussian pyramid to get similar results.
    # This pyramid-based result is a bit better than naive filters.
    h512 = content
    h256 = cv2.pyrDown(h512)
    h128 = cv2.pyrDown(h256)
    h64 = cv2.pyrDown(h128)
    h32 = cv2.pyrDown(h64)
    h16 = cv2.pyrDown(h32)
    c512, r512 = get_image_gradient(h512)
    c256, r256 = get_image_gradient(h256)
    c128, r128 = get_image_gradient(h128)
    c64, r64 = get_image_gradient(h64)
    c32, r32 = get_image_gradient(h32)
    c16, r16 = get_image_gradient(h16)
    c = c16
    c = d_resize(cv2.pyrUp(c), c32.shape) * 4.0 + c32
    c = d_resize(cv2.pyrUp(c), c64.shape) * 4.0 + c64
    c = d_resize(cv2.pyrUp(c), c128.shape) * 4.0 + c128
    c = d_resize(cv2.pyrUp(c), c256.shape) * 4.0 + c256
    c = d_resize(cv2.pyrUp(c), c512.shape) * 4.0 + c512
    r = r16
    r = d_resize(cv2.pyrUp(r), r32.shape) * 4.0 + r32
    r = d_resize(cv2.pyrUp(r), r64.shape) * 4.0 + r64
    r = d_resize(cv2.pyrUp(r), r128.shape) * 4.0 + r128
    r = d_resize(cv2.pyrUp(r), r256.shape) * 4.0 + r256
    r = d_resize(cv2.pyrUp(r), r512.shape) * 4.0 + r512
    coarse_effect_cols = c
    coarse_effect_rows = r

    # Normalization
    EPS = 1e-10
    max_effect = np.max((coarse_effect_cols**2 + coarse_effect_rows**2)**0.5)
    coarse_effect_cols = (coarse_effect_cols + EPS) / (max_effect + EPS)
    coarse_effect_rows = (coarse_effect_rows + EPS) / (max_effect + EPS)

    # Refinement
    stroke_density_scaled = (stroke_density.astype(np.float32) / 255.0).clip(0, 1)
    coarse_effect_cols *= (1.0 - stroke_density_scaled ** 2.0 + 1e-10) ** 0.5
    coarse_effect_rows *= (1.0 - stroke_density_scaled ** 2.0 + 1e-10) ** 0.5
    refined_result = np.stack([stroke_density_scaled, coarse_effect_rows, coarse_effect_cols], axis=2)

    return refined_result

# Global position of light source.
gx = 0.0
gy = 0.0

def run(image, mask, ambient_intensity, light_intensity, light_source_height, gamma_correction, stroke_density_clipping, light_color_red, light_color_green, light_color_blue, enabling_multiple_channel_effects):

    # Some pre-processing to resize images and remove input JPEG artifacts.
    raw_image = min_resize(image, 512)
    raw_image = raw_image.astype(np.float32)
    unmasked_image = raw_image.copy()

    if mask is not None:
        alpha = np.mean(d_resize(mask, raw_image.shape).astype(np.float32) / 255.0, axis=2, keepdims=True)
        raw_image = unmasked_image * alpha

    # Compute the convex-hull-like palette.
    h, w, c = raw_image.shape
    flattened_raw_image = raw_image.reshape((h * w, c))
    raw_image_center = np.mean(flattened_raw_image, axis=0)
    hull = ConvexHull(flattened_raw_image)
    
    import code
    code.interact(local=dict(globals(), **locals()))
    # Estimate the stroke density map.
    intersector = trimesh.Trimesh(faces=hull.simplices, vertices=hull.points).ray
    start = np.tile(raw_image_center[None, :], [h * w, 1])
    direction = flattened_raw_image - start
    print('Begin ray intersecting ...')
    index_tri, index_ray, locations = intersector.intersects_id(start, direction, return_locations=True, multiple_hits=True)
    
    print('Intersecting finished.')
    intersections = np.zeros(shape=(h * w, c), dtype=np.float32)
    intersection_count = np.zeros(shape=(h * w, 1), dtype=np.float32)
    CI = index_ray.shape[0]
    for c in range(CI):
        i = index_ray[c]
        intersection_count[i] += 1
        intersections[i] += locations[c]
    intersections = (intersections + 1e-10) / (intersection_count + 1e-10)
    intersections = intersections.reshape((h, w, 3))
    intersection_count = intersection_count.reshape((h, w))
    intersections[intersection_count < 1] = raw_image[intersection_count < 1]
    intersection_distance = np.sqrt(np.sum(np.square(intersections - raw_image_center[None, None, :]), axis=2, keepdims=True))
    pixel_distance = np.sqrt(np.sum(np.square(raw_image - raw_image_center[None, None, :]), axis=2, keepdims=True))
    stroke_density = ((1.0 - np.abs(1.0 - pixel_distance / intersection_distance)) * stroke_density_clipping).clip(0, 1) * 255

    # A trick to improve the quality of the stroke density map.
    # It uses guided filter to remove some possible artifacts.
    # You can remove these codes if you like sharper effects.
    guided_filter = createGuidedFilter(pixel_distance.clip(0, 255).astype(np.uint8), 1, 0.01)
    for _ in range(4):
        stroke_density = guided_filter.filter(stroke_density)

    # Visualize the estimated stroke density.
    cv2.imwrite('stroke_density.png', stroke_density.clip(0, 255).astype(np.uint8))

    # Then generate the lighting effects
    raw_image = unmasked_image.copy()
    lighting_effect = np.stack([
        generate_lighting_effects(stroke_density, raw_image[:, :, 0]),
        generate_lighting_effects(stroke_density, raw_image[:, :, 1]),
        generate_lighting_effects(stroke_density, raw_image[:, :, 2])
    ], axis=2)

    # Using a simple user interface to display results.

    def update_mouse(event, x, y, flags, param):
        global gx
        global gy
        gx = - float(x % w) / float(w) * 2.0 + 1.0
        gy = - float(y % h) / float(h) * 2.0 + 1.0
        return

    light_source_color = np.array([light_color_blue, light_color_green, light_color_red])

    global gx
    global gy

    while True:
        light_source_location = np.array([[[light_source_height, gy, gx]]], dtype=np.float32)
        light_source_direction = light_source_location / np.sqrt(np.sum(np.square(light_source_location)))
        final_effect = np.sum(lighting_effect * light_source_direction, axis=3).clip(0, 1)
        if not enabling_multiple_channel_effects:
            final_effect = np.mean(final_effect, axis=2, keepdims=True)
        rendered_image = (ambient_intensity + final_effect * light_intensity) * light_source_color * raw_image
        rendered_image = ((rendered_image / 255.0) ** gamma_correction) * 255.0
        canvas = np.concatenate([raw_image, rendered_image], axis=1).clip(0, 255).astype(np.uint8)
        
        import code
        code.interact(local=dict(globals(), **locals()))
    
        cv2.imshow('Move your mouse on the canvas to play!', canvas)
        cv2.setMouseCallback('Move your mouse on the canvas to play!', update_mouse)
        cv2.waitKey(10)
        
import numpy as np
import time
from skimage.color import rgb2grey, rgb2lab
from skimage.filters import laplace
from scipy.ndimage.filters import convolve

class Inpainter():
    def __init__(self, image, mask, patch_size=9, diff_algorithm='sq', plot_progress=False):
        self.image = image.astype('uint8')
        self.mask = mask.astype('uint8')
        # 进行光滑处理消除噪声
        self.mask = cv2.GaussianBlur(self.mask, (3, 3), 1.5)
        self.mask = (self.mask > 0).astype('uint8')
        self.fill_image = np.copy(self.image)
        self.fill_range = np.copy(self.mask)
        self.patch_size = patch_size
        # 信誉度
        self.confidence = (self.mask == 0).astype('float')
        self.height = self.mask.shape[0]
        self.width = self.mask.shape[1]
        self.total_fill_pixel = self.fill_range.sum()

        self.diff_algorithm = diff_algorithm
        self.plot_progress = plot_progress
        # 初始化成员变量

        # 边界矩阵
        self.front = None
        self.D = None
        # 优先级
        self.priority = None
        # 边界等照度线
        self.isophote = None
        # 目标点
        self.target_point = None
        # 灰度图片
        self.gray_image = None

    def inpaint(self):
        while self.fill_range.sum() != 0:
            self._get_front()
            self.gray_image = cv2.cvtColor(
                self.fill_image, cv2.COLOR_RGB2GRAY).astype('float')/255
            self._log()

            if self.plot_progress:
                self._plot_image()

            self._update_priority()
            target_point = self._get_target_point()
            self.target_point = target_point
            best_patch_range = self._get_best_patch_range(target_point)
            self._fill_image(target_point, best_patch_range)

        return self.fill_image

    # 打印日志

    def _log(self):
        progress_rate = 1-self.fill_range.sum()/self.total_fill_pixel
        progress_rate *= 100
        print('填充进度为%.2f' % progress_rate, '%')

    # 动态显示图片更新情况
    def _plot_image(self):
        fill_range = 1-self.fill_range
        fill_range = fill_range[:, :, np.newaxis].repeat(3, axis=2)

        image = self.fill_image*fill_range

        # 空洞填充为白色
        white_reginon = (self.fill_range-self.front)*255
        white_reginon = white_reginon[:, :, np.newaxis].repeat(3, axis=2)
        image += white_reginon

        plt.clf()
        plt.imshow(image)
        plt.draw()
        plt.pause(0.001)

    # 填充图片
    def _fill_image(self, target_point, source_patch_range):
        target_patch_range = self._get_patch_range(target_point)
        # 获取待填充点的位置
        fill_point_positions = np.where(self._patch_data(
            self.fill_range, target_patch_range) > 0)

        # 更新填充点的信誉度
        target_confidence = self._patch_data(
            self.confidence, target_patch_range)
        target_confidence[fill_point_positions[0], fill_point_positions[1]] =\
            self.confidence[target_point[0], target_point[1]]

        # 更新待填充点像素
        source_patch = self._patch_data(self.fill_image, source_patch_range)
        target_patch = self._patch_data(self.fill_image, target_patch_range)
        target_patch[fill_point_positions[0], fill_point_positions[1]] =\
            source_patch[fill_point_positions[0], fill_point_positions[1]]

        # 更新剩余填充点
        target_fill_range = self._patch_data(
            self.fill_range, target_patch_range)
        target_fill_range[:] = 0

    # 获取最佳匹配图片块的范围
    def _get_best_patch_range(self, template_point):
        diff_method_name = '_'+self.diff_algorithm+'_diff'
        diff_method = getattr(self, diff_method_name)

        template_patch_range = self._get_patch_range(template_point)
        patch_height = template_patch_range[0][1]-template_patch_range[0][0]
        patch_width = template_patch_range[1][1]-template_patch_range[1][0]

        best_patch_range = None
        best_diff = float('inf')
        lab_image = cv2.cvtColor(self.fill_image, cv2.COLOR_RGB2Lab)
        # lab_image=np.copy(self.fill_image)

        for x in range(self.height-patch_height+1):
            for y in range(self.width-patch_width+1):
                source_patch_range = [
                    [x, x+patch_height],
                    [y, y+patch_width]
                ]
                if self._patch_data(self.fill_range, source_patch_range).sum() != 0:
                    continue
                diff = diff_method(
                    lab_image, template_patch_range, source_patch_range)

                if diff < best_diff:
                    best_diff = diff
                    best_patch_range = source_patch_range

        return best_patch_range

    # 使用平方差比较算法计算两个区域的区别
    def _sq_diff(self, img, template_patch_range, source_patch_range):
        mask = 1-self._patch_data(self.fill_range, template_patch_range)
        mask = mask[:, :, np.newaxis].repeat(3, axis=2)
        template_patch = self._patch_data(img, template_patch_range)*mask
        source_patch = self._patch_data(img, source_patch_range)*mask

        return ((template_patch-source_patch)**2).sum()

    # 加入欧拉距离作为考量
    def _sq_with_eucldean_diff(self, img, template_patch_range, source_patch_range):
        sq_diff = self._sq_diff(img, template_patch_range, source_patch_range)
        eucldean_distance = np.sqrt((template_patch_range[0][0]-source_patch_range[0][0])**2 +
                                    (template_patch_range[1][0]-source_patch_range[1][0])**2)
        return sq_diff+eucldean_distance

    def _sq_with_gradient_diff(self, img, template_patch_range, source_patch_range):
        sq_diff = self._sq_diff(img, template_patch_range, source_patch_range)
        target_isophote = np.copy(
            self.isophote[self.target_point[0], self.target_point[1]])
        target_isophote_val = np.sqrt(
            target_isophote[0]**2+target_isophote[1]**2)
        gray_source_patch = self._patch_data(self.gray_image, source_patch_range)
        source_patch_gradient = np.nan_to_num(np.gradient(gray_source_patch))
        source_patch_val = np.sqrt(
            source_patch_gradient[0]**2+source_patch_gradient[1]**2)
        patch_max_pos = np.unravel_index(
            source_patch_val.argmax(),
            source_patch_val.shape
        )
        source_isophote = np.array([-source_patch_gradient[1, patch_max_pos[0], patch_max_pos[1]],
                                    source_patch_gradient[0, patch_max_pos[0], patch_max_pos[1]]])
        source_isophote_val = source_patch_val.max()

        # 计算两者之间的cos(theta)
        dot_product = abs(
            source_isophote[0]*target_isophote[0]+source_isophote[1] * target_isophote[1])
        norm = source_isophote_val*target_isophote_val
        cos_theta = 0
        if norm != 0:
            cos_theta = dot_product/norm
        val_diff = abs(source_isophote_val-target_isophote_val)
        return sq_diff-cos_theta+val_diff

    def _sq_with_gradient_eucldean_diff(self,img,template_patch_range,source_patch_range):
        sq_with_gradient=self._sq_with_gradient_diff(img,template_patch_range,source_patch_range)
        eucldean_distance = np.sqrt((template_patch_range[0][0]-source_patch_range[0][0])**2 +
                                    (template_patch_range[1][0]-source_patch_range[1][0])**2)
        return sq_with_gradient+eucldean_distance

    # 获取目标点的位置

    def _get_target_point(self):
        return np.unravel_index(self.priority.argmax(), self.priority.shape)

    # 使用Laplace算子求边界
    def _get_front(self):
        self.front = (cv2.Laplacian(self.fill_range, -1) > 0).astype('uint8')

    def _update_priority(self):
        self._update_front_confidence()
        self._update_D()
        self.priority = self.confidence*self.D*self.front

    # 更新D
    def _update_D(self):
        normal = self._get_normal()
        isophote = self._get_isophote()
        self.isophote = isophote
        self.D = abs(normal[:, :, 0]*isophote[:, :, 0]**2 +
                     normal[:, :, 1]*isophote[:, :, 1]**2)+0.001
    # 更新边界点的信誉度

    def _update_front_confidence(self):
        new_confidence = np.copy(self.confidence)
        front_positions = np.argwhere(self.front == 1)
        for point in front_positions:
            patch_range = self._get_patch_range(point)
            sum_patch_confidence = self._patch_data(
                self.confidence, patch_range).sum()
            area = (patch_range[0][1]-patch_range[0][0]) * \
                (patch_range[1][1]-patch_range[1][0])
            new_confidence[point[0], point[1]] = sum_patch_confidence/area

        self.confidence = new_confidence

    # 获取边界上法线的单位向量
    def _get_normal(self):
        x_normal = cv2.Scharr(self.fill_range, cv2.CV_64F, 1, 0)
        y_normal = cv2.Scharr(self.fill_range, cv2.CV_64F, 0, 1)
        normal = np.dstack([x_normal, y_normal])
        norm = np.sqrt(x_normal**2+y_normal**2).reshape(self.height,
                                                        self.width, 1).repeat(2, axis=2)
        norm[norm == 0] = 1
        unit_normal = normal/norm
        return unit_normal

    # 获取patch周围的等照度线
    def _get_isophote(self):
        gray_image = np.copy(self.gray_image)
        gray_image[self.fill_range == 1] = None
        gradient = np.nan_to_num(np.array(np.gradient(gray_image)))
        gradient_val = np.sqrt(gradient[0]**2 + gradient[1]**2)
        max_gradient = np.zeros([self.height, self.width, 2])
        front_positions = np.argwhere(self.front == 1)
        for point in front_positions:
            patch = self._get_patch_range(point)
            patch_y_gradient = self._patch_data(gradient[0], patch)
            patch_x_gradient = self._patch_data(gradient[1], patch)
            patch_gradient_val = self._patch_data(gradient_val, patch)
            patch_max_pos = np.unravel_index(
                patch_gradient_val.argmax(),
                patch_gradient_val.shape
            )
            # 旋转90度
            max_gradient[point[0], point[1], 0] = \
                -patch_y_gradient[patch_max_pos]
            max_gradient[point[0], point[1], 1] = \
                patch_x_gradient[patch_max_pos]

        return max_gradient

    # 获取图片块的范围
    def _get_patch_range(self, point):
        half_patch_size = (self.patch_size-1)//2
        patch_range = [
            [
                max(0, point[0]-half_patch_size),
                min(point[0]+half_patch_size+1, self.height)
            ],
            [
                max(0, point[1]-half_patch_size),
                min(point[1]+half_patch_size+1, self.width)
            ]
        ]
        return patch_range

    # 获取patch中的数据
    @staticmethod
    def _patch_data(img, patch_range):
        return img[patch_range[0][0]:patch_range[0][1], patch_range[1][0]:patch_range[1][1]]
        
def Patch(im, taillecadre, point):
    """
    Permet de calculer les deux points extreme du patch
    Voici le patch avec les 4 points
        1 _________ 2
          |        |
          |        |
         3|________|4
    """
    px, py = point
    xsize, ysize, c = im.shape
    x3 = max(px - taillecadre, 0)
    y3 = max(py - taillecadre, 0)
    x2 = min(px + taillecadre, ysize - 1)
    y2 = min(py + taillecadre, xsize - 1)
    return((x3, y3),(x2, y2))
    
def patch_complet(x, y, xsize, ysize, original):
    for i in range(xsize):
        for j in range(ysize):
            if original[x+i,y+j]==0:
                return(False)
    return(True)

def crible(xsize,ysize,x1,y1,masque):
    compteur=0
    cibles,ciblem=[],[]
    for i in range(xsize):
        for j in range(ysize):
            if masque[y1+i, x1+j] == 0:
                compteur += 1
                cibles+=[(i, j)]
            else:
                ciblem+=[(i, j)]
    return (compteur,cibles,ciblem,xsize,ysize)

def calculPatch(dOmega, cibleIndex, im, original, masque, taillecadre):
    mini = minvar = sys.maxsize
    sourcePatch,sourcePatche = [],[]
    p = dOmega[cibleIndex]
    patch = Patch(im, taillecadre, p)
    x1, y1 = patch[0]
    x2, y2 = patch[1]
    Xsize, Ysize, c = im.shape
    compteur,cibles,ciblem,xsize,ysize=crible(y2-y1+1,x2-x1+1,x1,y1,masque)
    for x in range(Xsize - xsize):
        for y in range(Ysize - ysize):
            if patch_complet(x, y, xsize, ysize, original):
                sourcePatch+=[(x, y)]
    for (y, x) in sourcePatch:
        R = V = B = ssd = 0
        for (i, j) in cibles:
            ima = im[y+i,x+j]
            omega = im[y1+i,x1+j]
            for k in range(3):
                difference = float(ima[k]) - float(omega[k])
                ssd += difference**2
            R += ima[0]
            V += ima[1]
            B += ima[2]
        ssd /= compteur
        if ssd < mini:
            variation = 0
            for (i, j) in ciblem:
                ima = im[y+i,x+j]
                differenceR = ima[0] - R/compteur
                differenceV = ima[1] - V/compteur
                differenceB = ima[2] - B/compteur
                variation += differenceR**2 + differenceV**2 + differenceB**2
            if ssd <  mini or variation < minvar:
                minvar = variation
                mini = ssd
                pointPatch = (x, y)
    return(ciblem, pointPatch)

Lap = np.array([[ 1.,  1.,  1.],[ 1., -8.,  1.],[ 1.,  1.,  1.]])
kerx = np.array([[ 0.,  0.,  0.], [-1.,  0.,  1.], [ 0.,  0.,  0.]])
kery = np.array([[ 0., -1.,  0.], [ 0.,  0.,  0.], [ 0.,  1.,  0.]])

def calculConfiance(confiance, im, taillecadre, masque, dOmega):
    """Permet de calculer la confiance définie dans l'article"""
    for k in range(len(dOmega)):
        px, py = dOmega[k]
        patch = Patch(im, taillecadre, dOmega[k])
        x3, y3 = patch[0]
        x2, y2 = patch[1]
        compteur = 0
        taille_psi_p = ((x2-x3+1) * (y2-y3+1))
        for x in range(x3, x2 + 1):
            for y in range(y3, y2 + 1):
                if masque[y, x] == 0: # intersection avec not Omega
                    compteur += confiance[y, x]
        confiance[py, px] = compteur / taille_psi_p
    return(confiance)

def calculData(dOmega, normale, data, gradientX, gradientY, confiance):
    """Permet de calculer data définie dans l'article"""
    for k in range(len(dOmega)):
        x, y = dOmega[k]
        NX, NY = normale[k]
        data[y, x] = (((gradientX[y, x] * NX)**2 + (gradientY[y, x] * NY)**2)**0.5) / 255.
    return(data)


def calculPriority(im, taillecadre, masque, dOmega, normale, data, gradientX, gradientY, confiance):
    """Permet de calculer la priorité du patch"""
    C = calculConfiance(confiance, im, taillecadre, masque, dOmega)
    D = calculData(dOmega, normale, data, gradientX, gradientY, confiance)
    index = 0
    maxi = 0
    for i in range(len(dOmega)):
        x, y = dOmega[i]
        P = C[y,x]*D[y,x]
        if P > maxi:
            maxi = P
            index = i
    return(C, D, index)
def update(im, gradientX, gradientY, confiance, source, masque, dOmega, point, list, index, taillecadre):
    p = dOmega[index]
    px, py = p
    patch = Patch(im, taillecadre, p)
    x1, y1 = patch[0]
    x2, y2 = patch[1]
    px, py = point
    for (i, j) in list:
        im[y1+i, x1+j] = im[py+i, px+j]
        confiance[y1+i, x1+j] = confiance[py, px]
        source[y1+i, x1+j] = 1
        masque[y1+i, x1+j] = 0
    return(im, gradientX, gradientY, confiance, source, masque)

Lap = np.array([[ 1.,  1.,  1.],[ 1., -8.,  1.],[ 1.,  1.,  1.]])
kerx = np.array([[ 0.,  0.,  0.], [-1.,  0.,  1.], [ 0.,  0.,  0.]])
kery = np.array([[ 0., -1.,  0.], [ 0.,  0.,  0.], [ 0.,  1.,  0.]])

def IdentifyTheFillFront(masque, source):
    """ Identifie le front de remplissage """
    dOmega = []
    normale = []
    lap = cv2.filter2D(masque, cv2.CV_32F, Lap)
    GradientX = cv2.filter2D(source, cv2.CV_32F, kerx)
    GradientY = cv2.filter2D(source, cv2.CV_32F, kery)
    xsize, ysize = lap.shape
    for x in range(xsize):
        for y in range(ysize):
            if lap[x, y] > 0:
                dOmega+=[(y, x)]
                dx = GradientX[x, y]
                dy = GradientY[x, y]
                N = (dy**2 + dx**2)**0.5
                if N != 0:
                    normale+=[(dy/N, -dx/N)]
                else:
                    normale+=[(dy, -dx)]
    return(dOmega, normale)
    
def inpaint(image, masque, taillecadre):
    xsize, ysize, channels = image.shape # meme taille pour filtre et image

    #on verifie les tailles

    x, y = masque.shape

    if x != xsize or y != ysize:
        print("La taille de l'image et du filtre doivent être les même")
        exit()

    tau = 170 #valeur pour séparer les valeurs du masque
    omega=[]
    confiance = np.copy(masque)
    masque = np.copy(masque)
    for x in range(xsize):
        for y in range(ysize):
            v=masque[x,y]
            if v<tau:
                omega.append([x,y])
                #image[x,y]=[255,255,255]
                masque[x,y]=1
                confiance[x,y]=0.
            else:
                masque[x,y]=0
                confiance[x,y]=1.

    source = np.copy(confiance)
    original= np.copy(confiance)
    dOmega = []
    normale = []


    im = np.copy(image)
    result = np.ndarray(shape = image.shape)


    data = np.ndarray(shape = image.shape[:2])
    Lap = np.array([[ 1.,  1.,  1.],[ 1., -8.,  1.],[ 1.,  1.,  1.]])
    kerx = np.array([[ 0.,  0.,  0.], [-1.,  0.,  1.], [ 0.,  0.,  0.]])
    kery = np.array([[ 0., -1.,  0.], [ 0.,  0.,  0.], [ 0.,  1.,  0.]])


    bool = True #pour le while
    print("Algorithme en fonctionnement")
    k=0

    niveau_de_gris = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)

    gradientX = np.float32(cv2.convertScaleAbs(cv2.Scharr(niveau_de_gris, cv2.CV_32F, 1, 0)))

    gradientY = np.float32(cv2.convertScaleAbs(cv2.Scharr(niveau_de_gris, cv2.CV_32F, 0, 1)))
    while bool:
        print(k)
        k+=1
        xsize, ysize = source.shape

        niveau_de_gris = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)

        gradientX = np.float32(cv2.convertScaleAbs(cv2.Scharr(niveau_de_gris, cv2.CV_32F, 1, 0)))

        gradientY = np.float32(cv2.convertScaleAbs(cv2.Scharr(niveau_de_gris, cv2.CV_32F, 0, 1)))

        for x in range(xsize):
            for y in range(ysize):
                if masque[x][y] == 1:
                    gradientX[x][y] = 0
                    gradientY[x][y] = 0
        gradienX, gradientY = gradientX/255, gradientY/255


        dOmega, normale = IdentifyTheFillFront(masque, source)


        confiance, data, index = calculPriority(im, taillecadre, masque, dOmega, normale, data, gradientX, gradientY, confiance)


        list, pp = calculPatch(dOmega, index, im, original, masque, taillecadre)


        im, gradientX, gradientY, confiance, source, masque = update(im, gradientX, gradientY, confiance, source, masque, dOmega, pp, list, index, taillecadre)

            # on verifie si on a fini
        bool = False
        for x in range(xsize):
            for y in range(ysize):
                if source[x, y] == 0:
                    bool = True

            # on enregistre a chaque fois pour voir l'avancée
        return im
        
def main():
    
    img_path = Path(r'D:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned\00302.jpg')
    dflimg = DFLIMG.load(img_path)
    img = cv2_imread(img_path)
    h,w,c = img.shape
    
    
    mask = dflimg.get_xseg_mask()
    #mask = cv2.resize(mask, (w,h), cv2.INTER_CUBIC )[...,None]

    cnts = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST , cv2.CHAIN_APPROX_TC89_KCOS  )
    
    # Get the largest found contour
    
    cnt = sorted(cnts[0], key = cv2.contourArea, reverse = True)#[0].squeeze()
    import code
    code.interact(local=dict(globals(), **locals()))
    screen = np.zeros_like( mask, np.uint8 )
    for x,y in cnt:
        cv2.circle(screen, (x,y), 1, (255,) )
        
    while True:
        cv2.imshow("", (mask*255).astype(np.uint8) )
        cv2.waitKey(0)
        cv2.imshow("", screen)
        cv2.waitKey(0)
        
    import code
    code.interact(local=dict(globals(), **locals()))
    
    center = np.mean(cnt,0)

    cnt2 = cnt.copy().astype(np.float32)

    cnt2_c = center - cnt2    
    cnt2_len = npla.norm(cnt2_c, axis=1, keepdims=True)
    cnt2_vec = cnt2_c / cnt2_len
    
    l,t = cnt.min(0)
    r,b = cnt.max(0)
    c = np.mean(cnt,0)
    cx, cy = c

    circle_rad = max( cy-t, b-cy, cx-l, r-cx )
    pts_count = 30

    circle_pts = c + circle_rad*np.array( [ [np.sin(i*2*math.pi/pts_count ),np.cos(i*2*math.pi/pts_count ) ] for i in range(pts_count) ] )
    circle_pts = circle_pts.astype(np.int32)

    circle_pts2 = c + circle_rad*0.9*np.array( [ [np.sin(i*2*math.pi/pts_count ),np.cos(i*2*math.pi/pts_count ) ] for i in range(pts_count) ] )
    circle_pts2 = circle_pts2.astype(np.int32)

    # Anchor perimeter
    pts_count = 120
    perim_pts = np.concatenate ( (np.concatenate ( [ np.arange(0,w+w/pts_count, w/pts_count)[...,None], np.array ( [[0]]*(pts_count+1) ) ], axis=-1 ),
                      np.concatenate ( [ np.arange(0,w+w/pts_count, w/pts_count)[...,None], np.array ( [[h]]*(pts_count+1) ) ], axis=-1 ),
                      np.concatenate ( [ np.array ( [[0]]*(pts_count+1) ), np.arange(0,h+h/pts_count, h/pts_count)[...,None] ], axis=-1 ),
                      np.concatenate ( [ np.array ( [[w]]*(pts_count+1) ), np.arange(0,h+h/pts_count, h/pts_count)[...,None] ], axis=-1 ) ), 0 ).astype(np.int32)


    cnt2 += cnt2_vec *  cnt2_len * 0.05
    cnt2 = cnt2.astype(np.int32)
    cnt2 = np.concatenate ( (cnt2, perim_pts), 0 )
    cnt = np.concatenate ( (cnt, perim_pts), 0 )
    #for x,y in np.concatenate( [circle_pts,  circle_pts2], 0 ):
    screen = np.zeros_like( mask, np.uint8 )
    for x,y in np.concatenate( [cnt,cnt2], 0 ):
        cv2.circle(screen, (x,y), 1, (255,) )



    #cv2.imshow("", screen)
    #cv2.waitKey(0)
    #import code
    #code.interact(local=dict(globals(), **locals()))


    #new_img = mls_rigid_deformation_inv( img, circle_pts, circle_pts2 )
    new_img = mls_rigid_deformation_inv( img, cnt, cnt2, density=0.5 )
    #new_img = mls_similarity_deformation_inv( img, cnt, cnt2 )
    
    
    while True:
        cv2.imshow("", img)
        cv2.waitKey(0)
        cv2.imshow("", new_img)
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))
    #===================================================
    
    
    image = cv2.imread(r'D:\DevelopPython\test\inpaint1.jpg')
    mask = cv2.imread(r'D:\DevelopPython\test\inpaint1_mask.jpg')[:,:,0]
    mask[mask > 0] = 255
    #import code
    #code.interact(local=dict(globals(), **locals()))
    #a = inpaint(image, mask, 9)
    
    a = Inpainter(image, mask).inpaint()
    
    cv2.imshow ("", np.clip(a, 0,255).astype(np.uint8) )
    cv2.waitKey(0)
            
    import code
    code.interact(local=dict(globals(), **locals()))
    #=======================================
    
    
    image = cv2.imread(r'D:\DevelopPython\test\00004.jpg')
    mask = None

    ambient_intensity = 0.45
    light_intensity = 1.0
    light_source_height = 1.0
    gamma_correction = 1.0
    stroke_density_clipping = 0.1
    enabling_multiple_channel_effects = False

    light_color_red = 1.0
    light_color_green = 1.0
    light_color_blue = 1.0

    run(image, mask, ambient_intensity, light_intensity, light_source_height,
        gamma_correction, stroke_density_clipping, light_color_red, light_color_green,
        light_color_blue, enabling_multiple_channel_effects)
        
    import code
    code.interact(local=dict(globals(), **locals()))
    #=======================================

    image_paths = pathex.get_image_paths(r"E:\FakeFaceVideoSources\Datasets\CelebA\aligned_def\aligned")
    image_paths_len = len(image_paths)

    while True:

        src1 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0
        src2 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0
        src3 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0

        dst1 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0
        dst2 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0
        dst3 = cv2_imread(image_paths[np.random.randint(image_paths_len)]).astype(np.float32) / 255.0

        while True:
            t = time.time()
            sot = imagelib.color_transfer_sot (src1, dst1, batch_size=30 )
            print(f'time took:{time.time()-t}')

            screen = np.concatenate([src1,dst1,sot], axis=0)


            cv2.imshow ("", np.clip(screen*255, 0,255).astype(np.uint8) )
            cv2.waitKey(0)


    import code
    code.interact(local=dict(globals(), **locals()))
    #=======================================
    
    img_path = Path(r'F:\DeepFaceLabCUDA9.2SSE\workspace ИНАУГ ГОЛ\data_dst\aligned\00001_0.jpg')
    dflimg = DFLIMG.load(img_path)
    img = cv2_imread(img_path)
    h,w,c = img.shape

    
    
    
    mask = dflimg.get_xseg_mask()
    mask = cv2.resize(mask, (w,h), cv2.INTER_CUBIC )[...,None]

    cnts = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST , cv2.CHAIN_APPROX_TC89_KCOS  )
    
    # Get the largest found contour
    cnt = sorted(cnts[0], key = cv2.contourArea, reverse = True)[0].squeeze()

    center = np.mean(cnt,0)

    cnt2 = cnt.copy().astype(np.float32)

    cnt2_c = center - cnt2    
    cnt2_len = npla.norm(cnt2_c, axis=1, keepdims=True)
    cnt2_vec = cnt2_c / cnt2_len
    
    l,t = cnt.min(0)
    r,b = cnt.max(0)
    c = np.mean(cnt,0)
    cx, cy = c

    circle_rad = max( cy-t, b-cy, cx-l, r-cx )
    pts_count = 30

    circle_pts = c + circle_rad*np.array( [ [np.sin(i*2*math.pi/pts_count ),np.cos(i*2*math.pi/pts_count ) ] for i in range(pts_count) ] )
    circle_pts = circle_pts.astype(np.int32)

    circle_pts2 = c + circle_rad*0.9*np.array( [ [np.sin(i*2*math.pi/pts_count ),np.cos(i*2*math.pi/pts_count ) ] for i in range(pts_count) ] )
    circle_pts2 = circle_pts2.astype(np.int32)

    # Anchor perimeter
    pts_count = 120
    perim_pts = np.concatenate ( (np.concatenate ( [ np.arange(0,w+w/pts_count, w/pts_count)[...,None], np.array ( [[0]]*(pts_count+1) ) ], axis=-1 ),
                      np.concatenate ( [ np.arange(0,w+w/pts_count, w/pts_count)[...,None], np.array ( [[h]]*(pts_count+1) ) ], axis=-1 ),
                      np.concatenate ( [ np.array ( [[0]]*(pts_count+1) ), np.arange(0,h+h/pts_count, h/pts_count)[...,None] ], axis=-1 ),
                      np.concatenate ( [ np.array ( [[w]]*(pts_count+1) ), np.arange(0,h+h/pts_count, h/pts_count)[...,None] ], axis=-1 ) ), 0 ).astype(np.int32)


    cnt2 += cnt2_vec *  cnt2_len * 0.05
    cnt2 = cnt2.astype(np.int32)
    cnt2 = np.concatenate ( (cnt2, perim_pts), 0 )
    cnt = np.concatenate ( (cnt, perim_pts), 0 )
    #for x,y in np.concatenate( [circle_pts,  circle_pts2], 0 ):
    screen = np.zeros_like( mask, np.uint8 )
    for x,y in np.concatenate( [cnt,cnt2], 0 ):
        cv2.circle(screen, (x,y), 1, (255,) )



    #cv2.imshow("", screen)
    #cv2.waitKey(0)
    #import code
    #code.interact(local=dict(globals(), **locals()))


    #new_img = mls_rigid_deformation_inv( img, circle_pts, circle_pts2 )
    new_img = mls_rigid_deformation_inv( img, cnt, cnt2, density=0.5 )
    #new_img = mls_similarity_deformation_inv( img, cnt, cnt2 )
    
    
    while True:
        cv2.imshow("", img)
        cv2.waitKey(0)
        cv2.imshow("", new_img)
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))
    #===================================================
    

    landmarks_2D = np.array([
        [ 0.000213256,  0.106454  ], #17
        [ 0.0752622,    0.038915  ], #18
        [ 0.18113,      0.0187482 ], #19
        [ 0.29077,      0.0344891 ], #20
        [ 0.393397,     0.0773906 ], #21
        [ 0.586856,     0.0773906 ], #22
        [ 0.689483,     0.0344891 ], #23
        [ 0.799124,     0.0187482 ], #24
        [ 0.904991,     0.038915  ], #25
        [ 0.98004,      0.106454  ], #26
        [ 0.490127,     0.203352  ], #27
        [ 0.490127,     0.307009  ], #28
        [ 0.490127,     0.409805  ], #29
        [ 0.490127,     0.515625  ], #30
        [ 0.36688,      0.587326  ], #31
        [ 0.426036,     0.609345  ], #32
        [ 0.490127,     0.628106  ], #33
        [ 0.554217,     0.609345  ], #34
        [ 0.613373,     0.587326  ], #35
        [ 0.121737,     0.216423  ], #36
        [ 0.187122,     0.178758  ], #37
        [ 0.265825,     0.179852  ], #38
        [ 0.334606,     0.231733  ], #39
        [ 0.260918,     0.245099  ], #40
        [ 0.182743,     0.244077  ], #41
        [ 0.645647,     0.231733  ], #42
        [ 0.714428,     0.179852  ], #43
        [ 0.793132,     0.178758  ], #44
        [ 0.858516,     0.216423  ], #45
        [ 0.79751,      0.244077  ], #46
        [ 0.719335,     0.245099  ], #47
        [ 0.254149,     0.780233  ], #48
        [ 0.340985,     0.745405  ], #49
        [ 0.428858,     0.727388  ], #50
        [ 0.490127,     0.742578  ], #51
        [ 0.551395,     0.727388  ], #52
        [ 0.639268,     0.745405  ], #53
        [ 0.726104,     0.780233  ], #54
        [ 0.642159,     0.864805  ], #55
        [ 0.556721,     0.902192  ], #56
        [ 0.490127,     0.909281  ], #57
        [ 0.423532,     0.902192  ], #58
        [ 0.338094,     0.864805  ], #59
        [ 0.290379,     0.784792  ], #60
        [ 0.428096,     0.778746  ], #61
        [ 0.490127,     0.785343  ], #62
        [ 0.552157,     0.778746  ], #63
        [ 0.689874,     0.784792  ], #64
        [ 0.553364,     0.824182  ], #65
        [ 0.490127,     0.831803  ], #66
        [ 0.42689 ,     0.824182  ]  #67
        ], dtype=np.float32)

    landmarks_2D *= 256
    screen = np.zeros( (256,256,1) , np.uint8 )

    for x,y in landmarks_2D:
        cv2.circle(screen, (x,y), 1, (255,) )

    cv2.imshow("", screen)
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    for image_path in pathex.get_image_paths(r'E:\FakeFaceVideoSources\Putin\Photo'):

        img = cv2.imread(image_path).astype(np.float32) / 255.0
        dflimg = DFLJPG.load ( image_path)

        img_size = 128
        face_mat = LandmarksProcessor.get_transform_mat( dflimg.get_landmarks(), img_size, FaceType.MOUTH, scale=1.0)
        wrp = cv2.warpAffine(img, face_mat, (img_size, img_size), cv2.INTER_LANCZOS4)

        cv2.imshow("", (wrp*255).astype(np.uint8) )
        cv2.waitKey(0)




    import code
    code.interact(local=dict(globals(), **locals()))

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    tf_sess = nn.tf_sess

    w = 64
    h = 64

    """
    triangles_count = 2
    triangles_np = np.array([ [ [0.0,0.0,-2.1],
                                [1.0,0.0,-2.1],
                                [0.0,1.0,-2.1] ],

                              [ [0.0,0.0,-2.0],
                                [1.0,1.0,-2.0],
                                [0.0,1.0,-2.0] ],

                            ], dtype=np.float32)

    triangles_colors_np = np.array([ [0.0,0.0,1.0],
                                     [0.0,1.0,0.0],
                                    ], dtype=np.float32)

    """

    triangles_count = 1

    triangles_np = np.array([ [ [-0.01,-0.01,-5.0],
                                [1.0,-0.01,-5.0],
                                [-0.01,1.0,-5.0] ],

                            ], dtype=np.float32)

    triangles_colors_np = np.array([ [0.0,1.0,0.0],
                                    ], dtype=np.float32)


    #camera_pos_np = np.array([ [0.0,0.0,0.0] ], dtype=np.float32)
    #camera_dir_np = np.array([ [0.0,0.0,-1.0] ], dtype=np.float32)
    #camera_pos_t = tf.placeholder(tf.float32, (3,) )
    #camera_dir_t = tf.placeholder(tf.float32, (3,) )

    # Create ray grid
    mh=0.5-np.linspace(0,1,h)
    mw=np.linspace(0,1,w)-0.5
    mw, mh = np.meshgrid(mw,mh)
    rd_np = np.concatenate( [ mw[...,None], mh[...,None], -np.ones_like(mw)[...,None] ] , -1 )
    rd_np /= np.linalg.norm(rd_np, axis=-1, keepdims=True)

    sun_dir_np = np.array ([0.0,0.0,-1.0], dtype=np.float32)

    ro_t = tf.zeros ( (h,w,3), tf.float32 ) #tf.placeholder(tf.float32, (h,w,3) )
    rd_t = tf.placeholder(tf.float32, (h,w,3) )

    sun_dir_t = tf.placeholder(tf.float32, (3,) )


    target_t = tf.placeholder(tf.float32, (h,w,3) )

    #triangles_t = tf.placeholder(tf.float32, (triangles_count,3,3) )
    triangles_t = tf.get_variable ("w", (triangles_count,3,3), dtype=nn.floatx)#, initializer=tf.initializers.zeros )
    nn.batch_set_value ( [(triangles_t, [ [ [-0.01,-0.01,-5.0],
                                            [1.0,-0.01,-5.0],
                                            [-0.01,1.0,-5.0] ],
                                        ] )] )

    triangles_colors_t = tf.placeholder(tf.float32, (triangles_count,3) )

    tris = tf.tile( triangles_t[None,None,...], (h,w,1,1,1) )


    ro_tris = tf.tile( ro_t[...,None,:], (1,1,triangles_count,1) )
    rd_tris = tf.tile( rd_t[...,None,:], (1,1,triangles_count,1) )

    # Ray triangle intersection
    # code borrowed from https://www.iquilezles.org/www/articles/intersectors/intersectors.htm
    # result is u,v,t per [h,w,tri]
    tris_v1v0 = tris[...,1,:] - tris[...,0,:]
    tris_v2v0 = tris[...,2,:] - tris[...,0,:]
    tris_rov0 = ro_tris-tris[:,:,:,0]

    tris_n = tf.linalg.cross (tris_v1v0, tris_v2v0)
    tris_q = tf.linalg.cross (tris_rov0, rd_tris)
    tris_d = 1.0 / tf.reduce_sum ( tf.multiply(rd_tris, tris_n), -1 )
    tris_u = tris_d * tf.reduce_sum ( tf.multiply(-tris_q, tris_v2v0), -1 )
    tris_v = tris_d * tf.reduce_sum ( tf.multiply(tris_q, tris_v1v0), -1 )
    tris_t = tris_d * tf.reduce_sum ( tf.multiply(-tris_n, tris_rov0), -1 )

    tris_n /= tf.linalg.norm(tris_n, axis=-1, keepdims=True)

    #tris_hit_pos = ro_tris+rd_tris*tris_t[...,None]

    #import code
    #code.interact(local=dict(globals(), **locals()))

    @tf.custom_gradient
    def z_one_clip(x):
        """
        x < 0   -> 0
        x >= 0  -> 1
        x >= 1  -> 0
        """
        #r = tf.clip_by_value ( tf.sign(x)+1, 0, 1 )
        r = tf.clip_by_value ( tf.sign(x)+tf.sign(x-1), -1, 1)
        x = 1-tf.abs(r)


        def grad(dy):
            return r#tf.clip_by_value ( tf.sign(x)+tf.sign(x-1), -1, 1)

        return x, grad

    # Invert distances, so the most near get highest value, and far starts from 1
    tris_f_t = tf.reduce_max ( tris_t, axis=-1, keepdims=True) - tris_t + 1


    # Apply UV clip : zeros t values which rays outside triangle
    #tris_uv_f_t = tf.reduce_min( tf.concat((        tris_u[...,None],
    #                                             (1-tris_u)[...,None],
    #                                                tris_v[...,None],
    #                                            (1-(tris_u+tris_v) )[...,None]
    #                                                ), -1), -1 )

    tris_f_t *= z_one_clip(tris_u)
    #tris_f_t *= z_one_clip(1-tris_u)
    tris_f_t *= z_one_clip(tris_v)
    tris_f_t *= z_one_clip(tris_u+tris_v)

    #tris_f_t *= z_one_clip(tris_uv_f_t)

    # Apply backplane clip : zeros tris_f_t by negative tris_t values
    #tris_f_t *= z_one_clip(tris_t)


    # Apply nearest tri clip
    #tris_inv_t *= tf.sign( tris_inv_t - tf.reduce_max ( tris_inv_t, axis=-1, keepdims=True) )+1
    #

    #tris_t = tf.clip_by_value( tf.sign( tris_inv_t - tf.reduce_max ( tris_inv_t, axis=-1, keepdims=True) )+1, 0, 1)
    #tris_t = tris_inv_t

    # Compute color
    tris_colors = tf.tile( triangles_colors_t[None,None,...], (h,w,1,1) )

    triangles_sun_dirs_t = tf.tile ( sun_dir_t[None,None,None,...], (h,w,triangles_count,1) )

    #dif_color * scene.sun_power * max(0.0, dot( normal, -scene.sun_dir ) )

    sun_dot = tf.reduce_sum ( tf.multiply(tris_n, -triangles_sun_dirs_t), -1, keepdims=True )#, 0, 1 )

    tris_t = tris_f_t #tf.clip_by_value( tf.sign(tris_f_t), 0, 1)

    x = tris_t[...,None]* tris_colors #* sun_dot
    #x = tris_t
    # Sum axis of all tris colors
    x = tf.reduce_sum(x, axis=-2)

    target_np = pickle.loads( Path(r'D:\tri.dat').read_bytes() )


    (xg,xv), = nn.gradients( tf.square(x-target_t) , [triangles_t])

    while True:
        r, rxg= nn.tf_sess.run([x,xg*-1], feed_dict={ rd_t : rd_np, sun_dir_t:sun_dir_np,
                                                            #triangles_t:triangles_np,
                                                            triangles_colors_t : triangles_colors_np,
                                                            target_t : target_np,
                                                            }

                                )

        cur_triangles_t =  nn.tf_sess.run(triangles_t)
        print(cur_triangles_t)

        cv2.imshow("", (r*255).astype(np.uint8) )
        cv2.waitKey(200)



        nn.batch_set_value ( [(triangles_t, cur_triangles_t+ rxg/10000.0) ] )


        #Path(r'D:\tri.dat').write_bytes( pickle.dumps(r) )

        #import code
        #code.interact(local=dict(globals(), **locals()))


    #=============================

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    tf_sess = nn.tf_sess

    var = tf.get_variable ("w", (1,), dtype=nn.floatx)#, initializer=tf.initializers.zeros )


    nn.batch_set_value ( [(var, [-5] )] )

    x = var

    #x = 1.0 / ( 1 + tf.exp(-100*(x-0.9)) )
    x = tf.abs(tf.nn.tanh( x ) )#*100-90 )

    #x = tf.abs( x )

    (xg,xv), = nn.gradients(x, [var])

    r = nn.tf_sess.run( [xg, x] )

    print(r)

    #cv2.imshow("", (result*255).astype(np.uint8) )
    #cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))

    #==================
    p = np.float32( [2,1] )

    pts = np.float32([ [0,0], [1,0], [2,0],[3,0] ])
    a = pts[:-1,:]
    b = pts[1:,:]
    edges = np.concatenate( ( pts[:-1,None,:], pts[1:,None,:] ), axis=-2)

    pa = p-a
    ba = b-a

    h = np.clip( np.einsum('ij,ij->i', pa, ba) / np.einsum('ij,ij->i', ba, ba), 0, 1 )

    x = npla.norm ( pa - ba*h[...,None], axis=1 )
    np.argmin(x)

    import code
    code.interact(local=dict(globals(), **locals()))

    """
    float sdSegment( in vec2 p, in vec2 a, in vec2 b )
    {
        vec2 pa = p-a, ba = b-a;
        float h = clamp( dot(pa,ba)/dot(ba,ba), 0.0, 1.0 );
        return length( pa - ba*h );
    }
    """

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    tf_sess = nn.tf_sess

    img = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0



    inp_t = tf.placeholder( tf.float32 , (None,None,None,None) )





    """
    weight = tf.constant (
         [
           [0.0, 1.0, 0.0],
           [1, -4.0, 1.0 ],
           [0.0, 1.0, 0.0],

          ], dtype=tf.float32)

    weight = tf.constant (
         [ [0.0, 0.0, 0.0, 0.0, 0.0],
           [0.0, -1.0, 2.0, -1.0, 0.0],
           [0.0, 2.0, -4.0, 2.0, 0.0],
           [0.0, -1.0, 2.0, -1.0, 0.0],
           [0.0, 0.0, 0.0, 0.0, 0.0],

          ], dtype=tf.float32)

    weight = tf.constant (
         [ [-1.0, 2.0, -2.0, 2.0, -1.0],
           [2.0, -6.0, 8.0, -6.0, 2.0],
           [-2.0, 8.0, -12.0, 8.0, -2.0],
           [2.0, -6.0, 8.0, -6.0, 2.0],
           [-1.0, 2.0, -2.0, 2.0, -1.0],

          ], dtype=tf.float32)
    """
    weight = tf.constant (
         [ [0.0, 0.0, -1.0, 0.0, 0.0],
           [0.0, -1.0, -2.0, -1.0, 0.0],
           [-1.0, -2.0, 16.0,- 2.0, -1.0],
           [0.0, -1.0, -2.0, -1.0, 0.0],
           [0.0, 0.0, -1.0, 0.0, 0.0],

          ], dtype=tf.float32)
    weight = weight [...,None,None]
    weight = tf.tile(weight, (1,1,3,1) )
    x = tf.nn.depthwise_conv2d(inp_t, weight, [1,1,1,1], 'SAME', data_format="NHWC")
    x = tf.reduce_mean( x, nn.conv2d_ch_axis, keepdims=True )
    x = tf.clip_by_value(x, 0, 1)


    result = tf_sess.run ( tf.reduce_sum(tf.abs(x)), feed_dict={  inp_t:img[None,...] }  )
    print(result)
    result = tf_sess.run (x, feed_dict={  inp_t:img[None,...] }  )

    #import code
    #code.interact(local=dict(globals(), **locals()))

    while True:
        cv2.imshow ("", np.clip(img*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)

        cv2.imshow ("", np.clip(result[0]*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)


    import code
    code.interact(local=dict(globals(), **locals()))

    ####################



    from core.imagelib import sd
    resolution = 256
    while True:
        circle_mask = sd.random_circle_faded ([resolution,resolution] )

        cv2.imshow ("", np.clip(circle_mask*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    """
    img = cv2_imread(r'D:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned\XSegDataset\obstructions\1.png').astype(np.float32) / 255.0

    a = img[...,3:4]
    a[a>0] = 1.0

    #a = cv2.dilate (a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(4,4)), iterations = 1 )
    #a = cv2.erode (a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(4,4)), iterations = 1 )

    cv2.imshow ("", np.clip(a*255, 0,255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))
    """
    #========================================================

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )


    generator = SampleGeneratorFaceSkinSegDataset(root_path=Path(r'D:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned'),
                                                debug=True,
                                                resolution=256,
                                                face_type=FaceType.WHOLE_FACE,
                                                batch_size=1,
                                                generators_count=1 )
    while True:
        img,mask = generator.generate_next()


        cv2.imshow ("", np.clip(img[0]*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)
        cv2.imshow ("", np.clip(mask[0]*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    #========================================================

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    tf_sess = nn.tf_sess

    #inp = tf.placehold
    resolution = 16

    def tf_random_1D_subline (len):

        low_bound = tf.random.uniform( (1,), maxval=len, dtype=tf.int32 )[0]
        high_bound = low_bound + tf.random.uniform( (1,), maxval=len-low_bound , dtype=tf.int32 )[0]
        return tf.range(low_bound, high_bound+1)[0]


    def tf_random_2D_patches (batch_size, resolution, ch, dtype=None, data_format=None):
        if dtype is None:
            dtype = tf.float32

        if data_format is None:
            data_format = nn.data_format

        if data_format == "NHWC":
            z = tf.zeros( (batch_size,resolution,resolution,ch), dtype=dtype )
        else:
            z = tf.zeros( (batch_size,ch,resolution,resolution), dtype=dtype )

        for i in range(batch_size):
            wr = tf_random_1D_subline(resolution)
            hr = tf_random_1D_subline(resolution)

            if data_format == "NHWC":
                z[i,hr,wr,:] = tf.constant ([1,1,1], dtype=dtype )
            else:
                z[i,:,hr,wr] = tf.constant ([1,1,1], dtype=dtype )

        return z

    x = tf_random_2D_patches (1, 16, 3)

    y = tf_sess.run ( x )
    print (y)

    import code
    code.interact(local=dict(globals(), **locals()))



    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )


    training_data_src_path = r'F:\DeepFaceLabCUDA9.2SSE\_internal\pretrain_CelebA'

    generator = SampleGeneratorFace(training_data_src_path, random_ct_samples_path=training_data_src_path, batch_size=1,
                        sample_process_options=SampleProcessor.Options(random_flip=True),
                        output_sample_types = [ {'sample_type': SampleProcessor.SampleType.FACE_IMAGE,'warp':False                      , 'transform':True, 'channel_type' : SampleProcessor.ChannelType.BGR, 'ct_mode': 'idt',  'face_type':FaceType.FULL, 'data_format':nn.data_format, 'resolution': 256},
                                                {'sample_type': SampleProcessor.SampleType.FACE_IMAGE,'warp':False                      , 'transform':True, 'channel_type' : SampleProcessor.ChannelType.BGR,                    'face_type':FaceType.FULL, 'data_format':nn.data_format, 'resolution': 256},
                                                {'sample_type': SampleProcessor.SampleType.FACE_MASK, 'warp':False                      , 'transform':True, 'channel_type' : SampleProcessor.ChannelType.G,   'face_mask_type' : SampleProcessor.FaceMaskType.FULL_FACE_EYES, 'face_type':FaceType.FULL, 'data_format':nn.data_format, 'resolution': 256},
                                              ],
                        generators_count=1 )
    while True:
        bgr,bgr_ct,mask = generator.generate_next()


        cv2.imshow ("", np.clip(bgr[0]*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)
        cv2.imshow ("", np.clip(bgr_ct[0]*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    #================


    #in_t = tf.placeholder(tf.float32, (2,3))
    #
    # Mask remain positive t values
    #tris_inv_t_mask = tf.clip_by_value( tf.sign(tris_inv_t), 0, 1 )

    # Filter nearest tri
    #tris_max_t = tf.reduce_max ( tris_t, axis=-1, keepdims=True)
    #tris_inv_t = tris_max_t - tris_t

    # Compute distance clip
    # Invert distances, so near get highest value

    #tris_max_t = tf.reduce_max ( tris_t, axis=-1, keepdims=True)
    #tris_inv_t = tris_max_t - tris_t

    # Cut distances by uv_cut, so unwanted tris get zero dist
    #tris_unwanted_cut = tris_inv_t * tris_uv_clip

    # Highest(near) t becomes 1, otherwise 0
    #tris_dist_clip = tf.sign( tris_unwanted_cut - tf.reduce_max ( tris_unwanted_cut, axis=-1, keepdims=True) )+1

    # Expand clip dims in order to mult on colors
    #x = tris_unwanted_cut[...,None] *  tris_dist_clip[...,None] * tris_uv_clip[...,None] * tris_colors

    import code
    code.interact(local=dict(globals(), **locals()))


    #=======================
    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )


    training_data_src_path = r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned'

    t = SampleProcessor.Types
    generator = SampleGeneratorFace(training_data_src_path, batch_size=1,
                        sample_process_options=SampleProcessor.Options(),
                        output_sample_types = [ {'types' : (t.IMG_WARPED_TRANSFORMED, t.FACE_TYPE_FULL, t.MODE_BGR), 'data_format':nn.data_format, 'resolution': 256 } ],
                        generators_count=1, rnd_seed=0 )

    while True:
        x = generator.generate_next()[0][0]

        cv2.imshow ("", np.clip(x*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)


    import code
    code.interact(local=dict(globals(), **locals()))

    #========================



    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    """
    class BilinearInterpolation(KL.Layer):
        def __init__(self, size=(2,2), **kwargs):
            self.size = size
            super(BilinearInterpolation, self).__init__(**kwargs)

        def compute_output_shape(self, input_shape):
            return (input_shape[0], input_shape[1]*self.size[1], input_shape[2]*self.size[0], input_shape[3])


        def call(self, X):
            _,h,w,_ = K.int_shape(X)

            #X = K.concatenate( [ X, X[:,:,-2:-1,:] ],axis=2 )
            #X = K.concatenate( [ X, X[:,:,-2:-1,:] ],axis=2 )
            #X = K.concatenate( [ X, X[:,-2:-1,:,:] ],axis=1 )
            #X = K.concatenate( [ X, X[:,-2:-1,:,:] ],axis=1 )

            X_sh = K.shape(X)
            batch_size, height, width, num_channels = X_sh[0], X_sh[1], X_sh[2], X_sh[3]

            output_h, output_w = (h*self.size[1], w*self.size[0])

            x_linspace = np.linspace(-1. , 1., output_w)#- 2/output_w
            y_linspace = np.linspace(-1. , 1., output_h)#

            x_coordinates, y_coordinates = np.meshgrid(x_linspace, y_linspace)
            x_coordinates = K.constant(x_coordinates, dtype=K.floatx() )
            y_coordinates = K.constant(y_coordinates, dtype=K.floatx() )



            x = x_coordinates
            y = y_coordinates

            x = .5 * (x + 1.0) * K.cast(width, dtype='float32')
            y = .5 * (y + 1.0) * K.cast(height, dtype='float32')
            x0 = K.cast(x, 'int32')
            x1 = x0 + 1
            y0 = K.cast(y, 'int32')
            y1 = y0 + 1
            max_x = int(K.int_shape(X)[2] -1)
            max_y = int(K.int_shape(X)[1] -1)

            x0 = K.clip(x0, 0, max_x)
            x1 = K.clip(x1, 0, max_x)
            y0 = K.clip(y0, 0, max_y)
            y1 = K.clip(y1, 0, max_y)


            pixels_batch = K.constant ( np.arange(0, batch_size) * (height * width), dtype=K.floatx() )

            pixels_batch = K.expand_dims(pixels_batch, axis=-1)

            base = K.tile(pixels_batch, (1, output_h * output_w ) )
            base = K.flatten(base)

            # base_y0 = base + (y0 * width)
            base_y0 = y0 * width
            base_y0 = base + base_y0
            # base_y1 = base + (y1 * width)
            base_y1 = y1 * width
            base_y1 = base_y1 + base

            indices_a = base_y0 + x0
            indices_b = base_y1 + x0
            indices_c = base_y0 + x1
            indices_d = base_y1 + x1

            flat_image = K.reshape(X, (-1, num_channels) )
            flat_image = K.cast(flat_image, dtype='float32')
            pixel_values_a = K.gather(flat_image, indices_a)
            pixel_values_b = K.gather(flat_image, indices_b)
            pixel_values_c = K.gather(flat_image, indices_c)
            pixel_values_d = K.gather(flat_image, indices_d)

            x0 = K.cast(x0, 'float32')
            x1 = K.cast(x1, 'float32')
            y0 = K.cast(y0, 'float32')
            y1 = K.cast(y1, 'float32')

            area_a = K.expand_dims(((x1 - x) * (y1 - y)), 1)
            area_b = K.expand_dims(((x1 - x) * (y - y0)), 1)
            area_c = K.expand_dims(((x - x0) * (y1 - y)), 1)
            area_d = K.expand_dims(((x - x0) * (y - y0)), 1)

            values_a = area_a * pixel_values_a
            values_b = area_b * pixel_values_b
            values_c = area_c * pixel_values_c
            values_d = area_d * pixel_values_d
            interpolated_image = values_a + values_b + values_c + values_d

            new_shape = (batch_size, output_h, output_w, num_channels)
            interpolated_image = K.reshape(interpolated_image, new_shape)

            #interpolated_image = interpolated_image[:,:-4,:-4,:]
            return interpolated_image

        def get_config(self):
            config = {"size": self.size}
            base_config = super(BilinearInterpolation, self).get_config()
            return dict(list(base_config.items()) + list(config.items()))

    def batch_dot(x, y, axes=None):
        if x.ndim < 2 or y.ndim < 2:
            raise ValueError('Batch dot requires inputs of rank 2 or more.')

        if isinstance(axes, int):
            axes = [axes, axes]
        elif isinstance(axes, tuple):
            axes = list(axes)

        if axes is None:
            if y.ndim == 2:
                axes = [x.ndim - 1, y.ndim - 1]
            else:
                axes = [x.ndim - 1, y.ndim - 2]

        if any([isinstance(a, (list, tuple)) for a in axes]):
            raise ValueError('Multiple target dimensions are not supported. ' +
                            'Expected: None, int, (int, int), ' +
                            'Provided: ' + str(axes))

        # Handle negative axes
        if axes[0] < 0:
            axes[0] += x.ndim
        if axes[1] < 0:
            axes[1] += y.ndim

        if 0 in axes:
            raise ValueError('Can not perform batch dot over axis 0.')

        if x.shape[0] != y.shape[0]:
            raise ValueError('Can not perform batch dot on inputs'
                            ' with different batch sizes.')

        d1 = x.shape[axes[0]]
        d2 = y.shape[axes[1]]
        if d1 != d2:
            raise ValueError('Can not do batch_dot on inputs with shapes ' +
                            str(x.shape) + ' and ' + str(y.shape) +
                            ' with axes=' + str(axes) + '. x.shape[%d] != '
                            'y.shape[%d] (%d != %d).' % (axes[0], axes[1], d1, d2))

        result = []
        axes = [axes[0] - 1, axes[1] - 1]  # ignore batch dimension
        for xi, yi in zip(x, y):
            result.append(np.tensordot(xi, yi, axes))
        result = np.array(result)

        if result.ndim == 1:
            result = np.expand_dims(result, -1)

        return result
    """
    def np_bilinear(X, size ):
        batch_size,h,w,num_channels = X.shape

        zero_h_line = np.zeros ( (batch_size,h,1,num_channels) )

        X = np.concatenate( [ zero_h_line, X ],axis=2 )
        X = np.concatenate( [ zero_h_line, X ],axis=2 )
        X = np.concatenate( [ X, zero_h_line ],axis=2 )
        X = np.concatenate( [ X, zero_h_line ],axis=2 )

        batch_size,h,w,num_channels = X.shape
        zero_w_line = np.zeros ( (batch_size,1,w,num_channels) )

        X = np.concatenate( [ zero_w_line, X ],axis=1 )
        X = np.concatenate( [ zero_w_line, X ],axis=1 )
        X = np.concatenate( [ X, zero_w_line ],axis=1 )
        X = np.concatenate( [ X, zero_w_line ],axis=1 )

        #import code
        #code.interact(local=dict(globals(), **locals()))

        batch_size,h,w,num_channels = X.shape

        output_w, output_h = size
        output_w += 4
        output_h += 4

        xc = np.linspace(0, w-1, w).astype(X.dtype)
        yc = np.linspace(0, h-1, h).astype(X.dtype)
        xc,yc = np.meshgrid (xc,yc)


        #x_linspace = np.linspace(-1., 1., output_w)
        #y_linspace = np.linspace(-1. , 1. - 2/output_h, output_h)#
        #x_coordinates, y_coordinates = np.meshgrid(x_linspace, y_linspace)

        #x = cv_x = cv2.resize (xc, (output_w,output_h) )
        #y = cv_y = cv2.resize (yc, (output_w,output_h) )
        x = np.linspace(0., w-1, output_w)
        y = np.linspace(0., h-1, output_h)
        x, y = np.meshgrid(x, y)

        aff = np.array (\
            [ [1,0,0],
              [0,1,0],
            ])
        #aff = cv2.getRotationMatrix2D( (0, 0), 60, 1.0)
        grids = np.stack ( [x,y,np.ones_like(x)] ).reshape ( (3,output_h*output_w)  )

        sampled_grids = np.dot(aff,grids).reshape ( (2,output_h,output_w)  )
        x = sampled_grids[0]
        y = sampled_grids[1]
        #import code
        #code.interact(local=dict(globals(), **locals()))

        #x = cv2.warpAffine(xc, cv2.getRotationMatrix2D( (w, h), 60, 1.0), (w, h) )
        #y = cv2.warpAffine(yc, cv2.getRotationMatrix2D( (w, h), 60, 1.0), (w, h) )

        x0 = x.astype(np.int32)
        x1 = x0 + 1
        y0 = y.astype(np.int32)
        y1 = y0 + 1

        ind_x0 = np.clip(x0,0,w-1)
        ind_x1 = np.clip(x1,0,w-1)
        ind_y0 = np.clip(y0,0,h-1)
        ind_y1 = np.clip(y1,0,h-1)

        indices_a = ind_y0 * w + ind_x0
        indices_b = ind_y1 * w + ind_x0
        indices_c = ind_y0 * w + ind_x1
        indices_d = ind_y1 * w + ind_x1

        flat_image = np.reshape(X, (-1, num_channels) )

        pixel_values_a = np.reshape( flat_image[np.ndarray.flatten (indices_a)], (output_h,output_w,num_channels) )
        pixel_values_b = np.reshape( flat_image[np.ndarray.flatten (indices_b)], (output_h,output_w,num_channels) )
        pixel_values_c = np.reshape( flat_image[np.ndarray.flatten (indices_c)], (output_h,output_w,num_channels) )
        pixel_values_d = np.reshape( flat_image[np.ndarray.flatten (indices_d)], (output_h,output_w,num_channels) )

        x0 = x0.astype(x.dtype)
        x1 = x1.astype(x.dtype)
        y0 = y0.astype(y.dtype)
        y1 = y1.astype(y.dtype)

        area_a = (x1 - x) * (y1 - y)
        area_b = (x1 - x) * (y - y0)
        area_c = (x - x0) * (y1 - y)
        area_d = (x - x0) * (y - y0)

        values_a = area_a[...,None] * pixel_values_a
        values_b = area_b[...,None] * pixel_values_b
        values_c = area_c[...,None] * pixel_values_c
        values_d = area_d[...,None] * pixel_values_d



        interpolated_image = values_a + values_b + values_c + values_d

        interpolated_image = interpolated_image[2:-2,2:-2,:]

        return interpolated_image


        #pixel_values_a = K.gather(flat_image, indices_a)
        #pixel_values_b = K.gather(flat_image, indices_b)
        #pixel_values_c = K.gather(flat_image, indices_c)
        #pixel_values_d = K.gather(flat_image, indices_d)



        new_shape = (batch_size, output_h, output_w, num_channels)
        interpolated_image = K.reshape(interpolated_image, new_shape)

        #interpolated_image = interpolated_image[:,:-4,:-4,:]
        return interpolated_image

    filepath =  r'D:\DevelopPython\test\00000.png'
    img = cv2.imread(filepath).astype(np.float32) / 255.0
    h,w,c = img.shape

    #img = np.random.random ( (4,4,3) )

    #xc = np.linspace(0, 4-1, 4)
    #yc = np.linspace(0, 4-1, 4)
    #xc,yc = np.meshgrid (xc,yc)
    #img = xc+yc
    #img = img[...,None]


    while True:
        random_w = 512#np.random.randint (1,128)
        random_h = 512#np.random.randint (1,128)

        np_x = np_bilinear(img[None,...], size=(random_w,random_h))
        cv_x = cv2.resize (img, (random_w,random_h))

        #import code
        #code.interact(local=dict(globals(), **locals()))

        print( np.sum(np.abs(np_x-cv_x)) )
        #import code
        #code.interact(local=dict(globals(), **locals()))

        cv2.imshow("", (np_x * 255).astype(np.uint8) )
        cv2.waitKey(0)

        cv2.imshow("", (cv_x * 255).astype(np.uint8) )
        cv2.waitKey(0)

    #import tensorflow as tf
    #tf_inp = tf.keras.Input ( (256,256,3) )
    #tf.keras.Input ( ())
    #tf_x = tf.image.resize_images (tf_inp, (512,512)  )
    #tf_unc = tf.keras.backend.function([tf_inp],[tf_x])
    #tf_x, = tf_unc ([ img[None,...]  ])

    inp = Input ( (256,256,3) )
    keras_x = BilinearInterpolation() ( inp )

    func = K.function([inp],[keras_x])


    #print (np.sum(np.abs(keras_x-tf_x)) )
    while True:
        keras_x, = func ([ img[None,...]  ])
        cv2.imshow("", (keras_x[0] * 255).astype(np.uint8) )
        cv2.waitKey(0)
        #cv2.imshow("", tf_x[0].astype(np.uint8) )
        #cv2.waitKey(0)


    #================================

    src_paths = pathex.get_image_paths(r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned')
    dst_paths = pathex.get_image_paths(r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_dst\aligned')

    dst_all = None
    dst_count = 0
    for path in io.progress_bar_generator (dst_paths, "Computing"):
        img = cv2_imread(path).astype(np.float32) / 255.0
        if dst_all is None:
            dst_all = img
        else:
            dst_all += img

        dst_count += 1

    dst_all /= dst_count
    dst_all = np.clip(dst_all, 0, 1)


    for path in io.progress_bar_generator (src_paths, "Computing"):
        img = cv2_imread(path).astype(np.float32) / 255.0

        ct = imagelib.color_transfer_idt(img, dst_all)

        cv2.imshow ("", np.clip(ct*255, 0,255).astype(np.uint8) )
        cv2.waitKey(0)

    cv2.imshow ("", np.clip(dst_all*255, 0,255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))



    lowests = []

    for src_path in io.progress_bar_generator (src_paths[0:10], "Computing"):
        dst_path = dst_paths[np.random.randint(dst_paths_len)]

        src_uint8 = cv2_imread(src_path)
        src = src_uint8.astype(np.float32) / 255.0

        dst_uint8 = cv2_imread(dst_path)
        dst = dst_uint8.astype(np.float32) / 255.0

        src_rct = imagelib.reinhard_color_transfer(src_uint8, dst_uint8).astype(np.float32) / 255.0
        src_lct = np.clip( imagelib.linear_color_transfer (src, dst), 0.0, 1.0 )
        src_mkl = imagelib.color_transfer_mkl (src, dst)
        src_idt = imagelib.color_transfer_idt (src, dst)
        src_sot = imagelib.color_transfer_sot (src, dst)

        dst_mean     = np.mean(dst, axis=(0,1) )
        src_mean     = np.mean(src, axis=(0,1) )
        src_rct_mean = np.mean(src_rct, axis=(0,1) )
        src_lct_mean = np.mean(src_lct, axis=(0,1) )
        src_mkl_mean = np.mean(src_mkl, axis=(0,1) )
        src_idt_mean = np.mean(src_idt, axis=(0,1) )
        src_sot_mean = np.mean(src_sot, axis=(0,1) )

        dst_std     = np.sqrt ( np.var(dst, axis=(0,1) ) + 1e-5 )
        src_std     = np.sqrt ( np.var(src, axis=(0,1) ) + 1e-5 )
        src_rct_std = np.sqrt ( np.var(src_rct, axis=(0,1) ) + 1e-5 )
        src_lct_std = np.sqrt ( np.var(src_lct, axis=(0,1) ) + 1e-5 )
        src_mkl_std = np.sqrt ( np.var(src_mkl, axis=(0,1) ) + 1e-5 )
        src_idt_std = np.sqrt ( np.var(src_idt, axis=(0,1) ) + 1e-5 )
        src_sot_std = np.sqrt ( np.var(src_sot, axis=(0,1) ) + 1e-5 )

        def_mean_sum = np.sum( np.square(src_mean-dst_mean) )
        rct_mean_sum = np.sum( np.square(src_rct_mean-dst_mean) )
        lct_mean_sum = np.sum( np.square(src_lct_mean-dst_mean) )
        mkl_mean_sum = np.sum( np.square(src_mkl_mean-dst_mean) )
        idt_mean_sum = np.sum( np.square(src_idt_mean-dst_mean) )
        sot_mean_sum = np.sum( np.square(src_sot_mean-dst_mean) )

        def_std_sum = np.sum( np.square(src_std-dst_std) )
        rct_std_sum = np.sum( np.square(src_rct_std-dst_std) )
        lct_std_sum = np.sum( np.square(src_lct_std-dst_std) )
        mkl_std_sum = np.sum( np.square(src_mkl_std-dst_std) )
        idt_std_sum = np.sum( np.square(src_idt_std-dst_std) )
        sot_std_sum = np.sum( np.square(src_sot_std-dst_std) )

        lowests.append([  def_mean_sum+def_std_sum,
                          rct_mean_sum+rct_std_sum,
                          lct_mean_sum+lct_std_sum,
                          mkl_mean_sum+mkl_std_sum,
                          idt_mean_sum+idt_std_sum,
                          sot_mean_sum+sot_std_sum
                        ])

        #cv2.imshow("", src_rct )
        #cv2.waitKey(0)


    np.mean(np.array(lowests), 0)


    #==========================================



    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf


    class ConvBlock(nn.ModelBase):

        def on_build(self, in_planes, out_planes):
            self.in_planes = in_planes
            self.out_planes = out_planes

            self.bn1 = nn.BatchNorm2D(in_planes)
            self.conv1 = nn.Conv2D (in_planes, out_planes//2, kernel_size=3, strides=1, padding='SAME', use_bias=False )

            self.bn2 = nn.BatchNorm2D(out_planes//2)
            self.conv2 = nn.Conv2D (out_planes//2, out_planes//4, kernel_size=3, strides=1, padding='SAME', use_bias=False )

            self.bn3 = nn.BatchNorm2D(out_planes//4)
            self.conv3 = nn.Conv2D (out_planes//4, out_planes//4, kernel_size=3, strides=1, padding='SAME', use_bias=False )

            if self.in_planes != self.out_planes:
                self.down_bn1 = nn.BatchNorm2D(in_planes)
                self.down_conv1 = nn.Conv2D (in_planes, out_planes, kernel_size=1, strides=1, padding='VALID', use_bias=False )
            else:
                self.down_bn1 = None
                self.down_conv1 = None

        def forward(self, input):
            x = input
            x = self.bn1(x)
            x = tf.nn.relu(x)
            x = out1 = self.conv1(x)

            x = self.bn2(x)
            x = tf.nn.relu(x)
            x = out2 = self.conv2(x)

            x = self.bn3(x)
            x = tf.nn.relu(x)
            x = out3 = self.conv3(x)
            x = tf.concat ([out1, out2, out3], axis=-1)

            if self.in_planes != self.out_planes:
                downsample = self.down_bn1(input)
                downsample = tf.nn.relu (downsample)
                downsample = self.down_conv1 (downsample)
                x = x + downsample
            else:
                x = x + input

            return x

    class HourGlass (nn.ModelBase):
        def on_build(self, in_planes, depth):
            self.b1 = ConvBlock (in_planes, 256)
            self.b2 = ConvBlock (in_planes, 256)

            if depth > 1:
                self.b2_plus = HourGlass(256, depth-1)
            else:
                self.b2_plus = ConvBlock(256, 256)

            self.b3 = ConvBlock(256, 256)

        def forward(self, input):
            up1 = self.b1(input)

            low1 = tf.nn.avg_pool(input, [1,2,2,1], [1,2,2,1], 'VALID')
            low1 = self.b2 (low1)

            low2 = self.b2_plus(low1)
            low3 = self.b3(low2)

            up2 = nn.upsample2d(low3)

            return up1+up2

    class FAN (nn.ModelBase):
        def __init__(self):
            super().__init__(name='FAN')

        def on_build(self):
            self.conv1 = nn.Conv2D (3, 64, kernel_size=7, strides=2, padding='SAME')
            self.bn1 = nn.BatchNorm2D(64)

            self.conv2 = ConvBlock(64, 128)
            self.conv3 = ConvBlock(128, 128)
            self.conv4 = ConvBlock(128, 256)

            self.m = []
            self.top_m = []
            self.conv_last = []
            self.bn_end = []
            self.l = []
            self.bl = []
            self.al = []
            for i in range(4):
                self.m += [ HourGlass(256, 4) ]
                self.top_m += [ ConvBlock(256, 256) ]

                self.conv_last += [ nn.Conv2D (256, 256, kernel_size=1, strides=1, padding='VALID') ]
                self.bn_end += [ nn.BatchNorm2D(256) ]

                self.l += [ nn.Conv2D (256, 68, kernel_size=1, strides=1, padding='VALID') ]

                if i < 4-1:
                    self.bl += [ nn.Conv2D (256, 256, kernel_size=1, strides=1, padding='VALID') ]
                    self.al += [ nn.Conv2D (68, 256, kernel_size=1, strides=1, padding='VALID') ]

        def forward(self, x) :
            x = self.conv1(x)
            x = self.bn1(x)
            x = tf.nn.relu(x)

            x = self.conv2(x)
            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], 'VALID')
            x = self.conv3(x)
            x = self.conv4(x)


            outputs = []
            previous = x
            for i in range(4):
                ll = self.m[i] (previous)

                ll = self.top_m[i] (ll)


                ll = self.conv_last[i] (ll)

                ll = self.bn_end[i] (ll)
                ll = tf.nn.relu(ll)

                tmp_out = self.l[i](ll)
                outputs.append(tmp_out)

                if i < 4 - 1:
                    ll = self.bl[i](ll)
                    previous = previous + ll + self.al[i](tmp_out)
            return outputs[-1]

    rnd_data = np.random.uniform (size=(1,3,256,256)).astype(np.float32)
    rnd_data = np.ones ((1,3,256,256)).astype(np.float32)
    rnd_data_tf = np.transpose(rnd_data, (0,2,3,1) )

    rnd_data_tf = cv2.imread ( r"D:\DevelopPython\test\00000.png" ).astype(np.float32) / 255.0
    rnd_data_tf = rnd_data_tf[None,...]
    rnd_data = np.transpose(rnd_data_tf, (0,3,1,2) )




    import torch
    import face_alignment
    fa = face_alignment.FaceAlignment(face_alignment.LandmarksType._3D,device='cpu').face_alignment_net
    fa.eval()

    #transfer weights
    def convd2d_from_torch(torch_layer):
        result = [ torch_layer.weight.data.numpy().transpose(2,3,1,0) ]
        if torch_layer.bias is not None:
            result +=  [ torch_layer.bias.data.numpy() ]
        return result

    def bn2d_from_torch(torch_layer):
        return [ torch_layer.weight.data.numpy(),
                 torch_layer.bias.data.numpy(),
                 torch_layer.running_mean.data.numpy(),
                 torch_layer.running_var.data.numpy(),
               ]

    def transfer_conv_block(dst,src):
        dst.bn1.set_weights ( bn2d_from_torch(src.bn1) )
        dst.conv1.set_weights ( convd2d_from_torch(src.conv1) )
        dst.bn2.set_weights ( bn2d_from_torch(src.bn2) )
        dst.conv2.set_weights ( convd2d_from_torch(src.conv2) )
        dst.bn3.set_weights ( bn2d_from_torch(src.bn3) )
        dst.conv3.set_weights ( convd2d_from_torch(src.conv3) )

        if dst.down_bn1 is not None:
            dst.down_bn1.set_weights ( bn2d_from_torch(src.downsample[0]) )
            dst.down_conv1.set_weights ( convd2d_from_torch(src.downsample[2]) )

    def transfer_hourglass(dst, src, level):

        transfer_conv_block (dst.b1, getattr (src, f'b1_{level}' ) )
        transfer_conv_block (dst.b2, getattr (src, f'b2_{level}' ) )

        if level > 1:
            transfer_hourglass (dst.b2_plus, src, level-1)
        else:
            transfer_conv_block (dst.b2_plus, getattr (src, f'b2_plus_{level}' ) )

        transfer_conv_block (dst.b3, getattr (src, f'b3_{level}' ) )


    with tf.device("/CPU:0"):
        FAN = FAN()
        #FAN.load_weights(r"D:\DevelopPython\test\2DFAN-4.npy")

        FAN.build()
        FAN.conv1.set_weights ( convd2d_from_torch(fa.conv1) )
        FAN.bn1.set_weights ( bn2d_from_torch(fa.bn1) )

        transfer_conv_block(FAN.conv2, fa.conv2)
        transfer_conv_block(FAN.conv3, fa.conv3)
        transfer_conv_block(FAN.conv4, fa.conv4)

        for i in range(4):
            transfer_hourglass(FAN.m[i], getattr(fa, f'm{i}'), 4)
            transfer_conv_block(FAN.top_m[i], getattr(fa, f'top_m_{i}'))

            FAN.conv_last[i].set_weights ( convd2d_from_torch( getattr(fa, f'conv_last{i}') ) )
            FAN.bn_end[i].set_weights ( bn2d_from_torch( getattr(fa, f'bn_end{i}') ) )
            FAN.l[i].set_weights ( convd2d_from_torch( getattr(fa, f'l{i}') ) )

            if i < 4-1:
                FAN.bl[i].set_weights ( convd2d_from_torch( getattr(fa, f'bl{i}') ) )
                FAN.al[i].set_weights ( convd2d_from_torch( getattr(fa, f'al{i}') ) )

        FAN.save_weights(r"D:\DevelopPython\test\3DFAN-4.npy")

    #import code
    #code.interact(local=dict(globals(), **locals()))



    def transform(point, center, scale, resolution):
        pt = np.array ( [point[0], point[1], 1.0] )
        h = 200.0 * scale
        m = np.eye(3)
        m[0,0] = resolution / h
        m[1,1] = resolution / h
        m[0,2] = resolution * ( -center[0] / h + 0.5 )
        m[1,2] = resolution * ( -center[1] / h + 0.5 )
        m = np.linalg.inv(m)
        return np.matmul (m, pt)[0:2]

    def get_pts_from_predict(a, center, scale):
        a_ch, a_h, a_w = a.shape

        b = a.reshape ( (a_ch, a_h*a_w) )
        c = b.argmax(1).reshape ( (a_ch, 1) ).repeat(2, axis=1).astype(np.float)
        c[:,0] %= a_w
        c[:,1] = np.apply_along_axis ( lambda x: np.floor(x / a_w), 0, c[:,1] )

        for i in range(a_ch):
            pX, pY = int(c[i,0]), int(c[i,1])
            if pX > 0 and pX < 63 and pY > 0 and pY < 63:
                diff = np.array ( [a[i,pY,pX+1]-a[i,pY,pX-1], a[i,pY+1,pX]-a[i,pY-1,pX]] )
                c[i] += np.sign(diff)*0.25

        c += 0.5

        return np.array( [ transform (c[i], center, scale, a_w) for i in range(a_ch) ] )


    tf_FAN_in = tf.placeholder(tf.float32, (1,256,256, 3))
    tf_FAN_out = FAN(tf_FAN_in)

    tf_x = nn.tf_sess.run(tf_FAN_out, feed_dict={tf_FAN_in:rnd_data_tf} )[0]

    fa_out_tensor = fa( torch.autograd.Variable( torch.from_numpy(rnd_data), volatile=True) )[-1][0].data.cpu()
    torch_x = fa_out_tensor.numpy()
    torch_x = np.transpose (torch_x, (1,2,0))

    diff = np.mean(np.abs(tf_x-torch_x))
    print (f"diff = {diff}")

    tf_p = get_pts_from_predict(tf_x, [127.0,127.0], 1.0)
    torch_p = get_pts_from_predict(torch_x, [127.0,127.0], 1.0)

    import code
    code.interact(local=dict(globals(), **locals()))

    #========================

    ct_1_filepath =  r'E:\FakeFaceVideoSources\Datasets\CelebA\aligned_def\aligned\00001.jpg'
    ct_1_img = cv2.imread(ct_1_filepath).astype(np.float32) / 255.0
    ct_1_img_shape = ct_1_img.shape
    ct_1_dflimg = DFLJPG.load ( ct_1_filepath)


    face_mat = LandmarksProcessor.get_transform_mat( ct_1_dflimg.get_landmarks(), 256, FaceType.HEAD)

    import code
    code.interact(local=dict(globals(), **locals()))



    def channel_hist_match(source, template, hist_match_threshold=255, mask=None):
        # Code borrowed from:
        # https://stackoverflow.com/questions/32655686/histogram-matching-of-two-images-in-python-2-x
        masked_source = source
        masked_template = template

        if mask is not None:
            masked_source = source * mask
            masked_template = template * mask

        oldshape = source.shape
        source = source.ravel()
        template = template.ravel()
        masked_source = masked_source.ravel()
        masked_template = masked_template.ravel()
        s_values, bin_idx, s_counts = np.unique(source, return_inverse=True,
                                                return_counts=True)
        t_values, t_counts = np.unique(template, return_counts=True)

        s_quantiles = np.cumsum(s_counts).astype(np.float64)
        s_quantiles = hist_match_threshold * s_quantiles / s_quantiles[-1]
        t_quantiles = np.cumsum(t_counts).astype(np.float64)
        t_quantiles = 255 * t_quantiles / t_quantiles[-1]
        interp_t_values = np.interp(s_quantiles, t_quantiles, t_values)

        return interp_t_values[bin_idx].reshape(oldshape)

    img = cv2.imread(r'D:\DevelopPython\test\ct_src.jpg').astype(np.float32) / 255.0

    while True:

        np_rnd = np.random.rand



        inBlack  = np.array([np_rnd()*0.25    , np_rnd()*0.25    , np_rnd()*0.25], dtype=np.float32)
        inWhite  = np.array([1.0-np_rnd()*0.25, 1.0-np_rnd()*0.25, 1.0-np_rnd()*0.25], dtype=np.float32)
        inGamma  = np.array([0.5+np_rnd(), 0.5+np_rnd(), 0.5+np_rnd()], dtype=np.float32)
        outBlack = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        outWhite = np.array([1.0, 1.0, 1.0], dtype=np.float32)

        img2 = ( ( (img - inBlack) / (inWhite - inBlack) ) ** (1/inGamma) ) *  (outWhite - outBlack) + outBlack
        img2 = np.clip(img2, 0, 1)


        #cv2.imshow("", img)
        #cv2.waitKey(0)
        cv2.imshow("", (img2*255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))



    """
    inBlack = 23.0
    inWhite = 190.0
    inGamma = 1.61
    outBlack = 0.0
    outWhite = 255.0
    vec3 inPixel = source.rgb;
    vec3 outPixel = (pow(((inPixel * 255.0) - vec3(inBlack)) / (inWhite - inBlack), vec3(inGamma)) * (outWhite - outBlack) + outBlack) / 255.0;



    lut_in = [0, 127, 255]
    lut_out = [50, 127, 255]
    lut_8u = np.interp(np.arange(0, 256), lut_in, lut_out).astype(np.uint8)
    img2 = cv2.LUT(img, lut_8u)

    s = img.ravel()
    s_values, bin_idx, s_counts = np.unique(s, return_inverse=True, return_counts=True)
    s_quantiles = np.cumsum(s_counts).astype(np.float64)
    s_quantiles = 255 * s_quantiles / s_quantiles[-1]

    interp_t_values = np.interp(s_quantiles, s_quantiles, s_values)

    d = s_quantiles[bin_idx].reshape(s.shape)

    image_histogram, bins = np.histogram(s, 255, density=True)
    """

    import code
    code.interact(local=dict(globals(), **locals()))

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.CPU() )
    tf = nn.tf

    img = cv2.imread(r'D:\DevelopPython\test\mask_0.png')[...,0:1].astype(np.float32) / 255.0

    t = time.time()

    ero_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(15,15))

    cv_erode = cv2.erode(img, ero_k, iterations = 1 )
    print(f"time {time.time() - t}")


    inp_t = tf.placeholder( tf.float32, (None,None,None,None) )

    eroded_t = tf.nn.erosion2d(inp_t, ero_k[...,None].astype(np.float32), strides=[1,1,1,1], rates=[1,1,1,1], padding="SAME")
    eroded_t = eroded_t - tf.ones_like(inp_t)

    t = time.time()
    tf_erode = nn.tf_sess.run (eroded_t , feed_dict={inp_t: img[None,...] } )
    print(f"time {time.time() - t}")

    while True:
        cv2.imshow("", (cv_erode*255).astype(np.uint8))
        cv2.waitKey(0)
        cv2.imshow("", (tf_erode[0]*255).astype(np.uint8))
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))




    src_paths = pathex.get_image_paths(r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_src\aligned')
    dst_paths = pathex.get_image_paths(r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_dst\aligned')

    best_ct = CTComputerSubprocessor(src_paths, dst_paths).run()

    print(f"best ct_mode is >> {best_ct} <<")
    import code
    code.interact(local=dict(globals(), **locals()))



    lowests = []

    for src_path in io.progress_bar_generator (src_paths[0:10], "Computing"):
        dst_path = dst_paths[np.random.randint(dst_paths_len)]

        src_uint8 = cv2_imread(src_path)
        src = src_uint8.astype(np.float32) / 255.0

        dst_uint8 = cv2_imread(dst_path)
        dst = dst_uint8.astype(np.float32) / 255.0

        src_rct = imagelib.reinhard_color_transfer(src_uint8, dst_uint8).astype(np.float32) / 255.0
        src_lct = np.clip( imagelib.linear_color_transfer (src, dst), 0.0, 1.0 )
        src_mkl = imagelib.color_transfer_mkl (src, dst)
        src_idt = imagelib.color_transfer_idt (src, dst)
        src_sot = imagelib.color_transfer_sot (src, dst)

        dst_mean     = np.mean(dst, axis=(0,1) )
        src_mean     = np.mean(src, axis=(0,1) )
        src_rct_mean = np.mean(src_rct, axis=(0,1) )
        src_lct_mean = np.mean(src_lct, axis=(0,1) )
        src_mkl_mean = np.mean(src_mkl, axis=(0,1) )
        src_idt_mean = np.mean(src_idt, axis=(0,1) )
        src_sot_mean = np.mean(src_sot, axis=(0,1) )

        dst_std     = np.sqrt ( np.var(dst, axis=(0,1) ) + 1e-5 )
        src_std     = np.sqrt ( np.var(src, axis=(0,1) ) + 1e-5 )
        src_rct_std = np.sqrt ( np.var(src_rct, axis=(0,1) ) + 1e-5 )
        src_lct_std = np.sqrt ( np.var(src_lct, axis=(0,1) ) + 1e-5 )
        src_mkl_std = np.sqrt ( np.var(src_mkl, axis=(0,1) ) + 1e-5 )
        src_idt_std = np.sqrt ( np.var(src_idt, axis=(0,1) ) + 1e-5 )
        src_sot_std = np.sqrt ( np.var(src_sot, axis=(0,1) ) + 1e-5 )

        def_mean_sum = np.sum( np.square(src_mean-dst_mean) )
        rct_mean_sum = np.sum( np.square(src_rct_mean-dst_mean) )
        lct_mean_sum = np.sum( np.square(src_lct_mean-dst_mean) )
        mkl_mean_sum = np.sum( np.square(src_mkl_mean-dst_mean) )
        idt_mean_sum = np.sum( np.square(src_idt_mean-dst_mean) )
        sot_mean_sum = np.sum( np.square(src_sot_mean-dst_mean) )

        def_std_sum = np.sum( np.square(src_std-dst_std) )
        rct_std_sum = np.sum( np.square(src_rct_std-dst_std) )
        lct_std_sum = np.sum( np.square(src_lct_std-dst_std) )
        mkl_std_sum = np.sum( np.square(src_mkl_std-dst_std) )
        idt_std_sum = np.sum( np.square(src_idt_std-dst_std) )
        sot_std_sum = np.sum( np.square(src_sot_std-dst_std) )

        lowests.append([  def_mean_sum+def_std_sum,
                          rct_mean_sum+rct_std_sum,
                          lct_mean_sum+lct_std_sum,
                          mkl_mean_sum+mkl_std_sum,
                          idt_mean_sum+idt_std_sum,
                          sot_mean_sum+sot_std_sum
                        ])

        #cv2.imshow("", src_rct )
        #cv2.waitKey(0)


    np.mean(np.array(lowests), 0)

    import code
    code.interact(local=dict(globals(), **locals()))

    img = cv2.imread(r'D:\DevelopPython\test\ct_src.jpg').astype(np.float32) / 255.0
    img2 = cv2.imread(r'D:\DevelopPython\test\ct_trg.jpg').astype(np.float32) / 255.0
    #img = img[...,::-1]
    #img2 = img2[...,::-1]
    def clr(source,target):
        rgb_s = source.reshape ( (-1,3) )
        rgb_t = target.reshape ( (-1,3) )

        mean_s = np.mean(rgb_s, 0)
        mean_t = np.mean(rgb_t, 0)

        cov_s = np.cov( rgb_s.T )
        cov_t = np.cov( rgb_t.T )

        U_s, A_s, _ = np.linalg.svd(cov_s)
        U_t, A_t, _ = np.linalg.svd(cov_t)

        rgbh_s = np.concatenate ( [rgb_s, np.ones( (rgb_s.shape[0], 1), dtype=np.float32)], -1 )
        T_t = np.eye(4)
        T_t[0:3,3] = mean_t
        T_s = np.eye(4)
        T_s[0:3,3] = -mean_s

        R_t = scipy.linalg.block_diag(U_t, 1)
        R_s = scipy.linalg.block_diag(np.linalg.inv(U_s), 1)

        S_t = scipy.linalg.block_diag ( np.diag( A_t ** (0.5) ), 1)
        S_s = scipy.linalg.block_diag ( np.diag( A_s ** (-0.5) ), 1)

        rgbh_e = np.dot(np.dot(np.dot(np.dot(np.dot(np.dot(T_t, R_t),S_t),S_s),R_s),T_s),rgbh_s.T)

        result = rgbh_e.T[...,0:3].reshape(source.shape )
        result = np.clip(result, 0, 1)
        return result
        import code
        code.interact(local=dict(globals(), **locals()))

    c2 = clr(img,img2)

    from core.imagelib import color_transfer_mkl
    c = color_transfer_mkl(img,img2)


    cv2.imshow("", (img*255).astype(np.uint8) )
    cv2.waitKey(0)
    cv2.imshow("", (img2*255).astype(np.uint8) )
    cv2.waitKey(0)
    while True:
        cv2.imshow("", (c*255).astype(np.uint8) )
        cv2.waitKey(0)
        cv2.imshow("", (c2*255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.CPU() )
    tf = nn.tf

    """
    def tf_channel_histogram (input, bins, data_range):
        range_min, range_max = data_range

        bin_range = (range_max-range_min) / (bins-1)
        reduce_axes = [*range(input.shape.ndims)][1:]
        ones_mask = tf.ones_like(input)
        zero_mask = tf.zeros_like(input)

        x = input
        x += bin_range

        output = []

        for i in range(bins, 0, -1):
            cond = tf.greater_equal(x, i*bin_range )
            x_ones = tf.where (cond, ones_mask, zero_mask )
            x_zeros = tf.where (cond, zero_mask, ones_mask )
            x = x * x_zeros
            output.append ( tf.expand_dims(tf.reduce_sum (x_ones, axis=reduce_axes ), -1) )

        return tf.concat(output[::-1],-1)
    """
    def channel_hist_match(source, template, hist_match_threshold=255, mask=None):
        masked_source = source
        masked_template = template

        if mask is not None:
            masked_source = source * mask
            masked_template = template * mask

        oldshape = source.shape
        source = source.ravel()
        template = template.ravel()
        masked_source = masked_source.ravel()
        masked_template = masked_template.ravel()
        s_values, bin_idx, s_counts = np.unique(source, return_inverse=True,
                                                return_counts=True)
        t_values, t_counts = np.unique(template, return_counts=True)

        import code
        code.interact(local=dict(globals(), **locals()))
        s_quantiles = np.cumsum(s_counts).astype(np.float64)
        s_quantiles = hist_match_threshold * s_quantiles / s_quantiles[-1]
        t_quantiles = np.cumsum(t_counts).astype(np.float64)
        t_quantiles = 255 * t_quantiles / t_quantiles[-1]
        interp_t_values = np.interp(s_quantiles, t_quantiles, t_values)

        return interp_t_values[bin_idx].reshape(oldshape)

    def tf_channel_histogram (input, bins, data_range):
        range_min, range_max = data_range
        bin_range = (range_max-range_min) / (bins-1)
        reduce_axes = [*range(input.shape.ndims)][1:]
        x = input
        x += bin_range/2
        output = []
        for i in range(bins-1, -1, -1):
            y = x - (i*bin_range)
            ones_mask = tf.sign( tf.nn.relu(y) )
            x = x * (1.0 - ones_mask)
            output.append ( tf.expand_dims(tf.reduce_sum (ones_mask, axis=reduce_axes ), -1) )
        return tf.concat(output[::-1],-1)

    def tf_histogram(input, bins=256, data_range=(0,1.0)):
        return tf.concat ( [tf.expand_dims( tf_channel_histogram( input[...,i], bins=bins, data_range=data_range ), -1 ) for i in range(input.shape[-1])], -1 )

    img = cv2.imread(r'D:\DevelopPython\test\00000.png')#.astype(np.float32) / 255.0
    img2 = cv2.imread(r'D:\DevelopPython\test\00004.jpg')#.astype(np.float32)

    x = channel_hist_match(img,img2)
    import code
    code.interact(local=dict(globals(), **locals()))
    nph = np.histogram(img[...,0], bins=256, range=(0,1.0) )

    inp_t = tf.placeholder( tf.float32, (None,None,None) )
    hist_t = tf_channel_histogram(inp_t, bins=256, data_range=(0,1.0) )
    #hist_t = tf_histogram(inp_t, bins=256, data_range=(0,1.0) )

    tfh = nn.tf_sess.run (hist_t , feed_dict={inp_t: img[None,...,0]  } )

    import code
    code.interact(local=dict(globals(), **locals()))

    from core.leras import nn
    nn.initialize_main_env()
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf

    def tf_suppress_half_mean(t, eps=0.00001):
        if t.shape.ndims != 1:
            raise ValueError("tf_suppress_half_mean: t rank must be 1")
        t_mean_eps = tf.reduce_mean(t) - eps
        q = tf.clip_by_value(t, t_mean_eps, tf.reduce_max(t) )
        q = tf.clip_by_value(q-t_mean_eps, 0, eps)
        q = q * (t/eps)
        return q

    inp = tf.placeholder( tf.float32, (None,) )
    res = tf_suppress_half_mean(inp)

    x = nn.tf_sess.run (res , feed_dict={inp: np.array([1,2,3,4])  } )
    print(x)
    import code
    code.interact(local=dict(globals(), **locals()))

    from core.leras import nn
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf


    img = cv2.imread ( r"D:\DevelopPython\test\images\96x96_0.png" ).astype(np.float32) / 255.0
    from facelib import FaceEnhancer
    fe = FaceEnhancer()
    img_enh = fe.enhance(img, preserve_size=True)

    while True:
        cv2.imshow ("", (img*255).astype(np.uint8) )
        cv2.waitKey(0)

        cv2.imshow ("", (img_enh*255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))



    from core.leras import nn
    nn.initialize( device_config=nn.DeviceConfig.BestGPU() )

    tf = nn.tf


    def load_pb(path_to_pb):
        with tf.gfile.GFile(path_to_pb, "rb") as f:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(f.read())
        with tf.Graph().as_default() as graph:
            tf.import_graph_def(graph_def, name='')
            return graph

    graph = load_pb (r"D:\DevelopPython\test\giga.pb")

    sess = tf.Session(graph=graph, config=nn.tf_sess_config)

    def get_op_value(op_name, n_output=0):
        return sess.run ([ graph.get_operation_by_name(op_name).outputs[n_output] ])[0].astype(np.float32)


    class FaceEnhancer (nn.ModelBase):
        def __init__(self, name='FaceEnhancer'):
            super().__init__(name=name)

        def on_build(self):
            self.conv1 = nn.Conv2D (3, 64, kernel_size=3, strides=1, padding='SAME')

            self.dense1 = nn.Dense (1, 64, use_bias=False)
            self.dense2 = nn.Dense (1, 64, use_bias=False)

            self.e0_conv0 = nn.Conv2D (64, 64, kernel_size=3, strides=1, padding='SAME')
            self.e0_conv1 = nn.Conv2D (64, 64, kernel_size=3, strides=1, padding='SAME')

            self.e1_conv0 = nn.Conv2D (64, 112, kernel_size=3, strides=1, padding='SAME')
            self.e1_conv1 = nn.Conv2D (112, 112, kernel_size=3, strides=1, padding='SAME')

            self.e2_conv0 = nn.Conv2D (112, 192, kernel_size=3, strides=1, padding='SAME')
            self.e2_conv1 = nn.Conv2D (192, 192, kernel_size=3, strides=1, padding='SAME')

            self.e3_conv0 = nn.Conv2D (192, 336, kernel_size=3, strides=1, padding='SAME')
            self.e3_conv1 = nn.Conv2D (336, 336, kernel_size=3, strides=1, padding='SAME')

            self.e4_conv0 = nn.Conv2D (336, 512, kernel_size=3, strides=1, padding='SAME')
            self.e4_conv1 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')

            self.center_conv0 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')
            self.center_conv1 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')
            self.center_conv2 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')
            self.center_conv3 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')

            self.d4_conv0 = nn.Conv2D (1024, 512, kernel_size=3, strides=1, padding='SAME')
            self.d4_conv1 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')

            self.d3_conv0 = nn.Conv2D (848, 512, kernel_size=3, strides=1, padding='SAME')
            self.d3_conv1 = nn.Conv2D (512, 512, kernel_size=3, strides=1, padding='SAME')

            self.d2_conv0 = nn.Conv2D (704, 288, kernel_size=3, strides=1, padding='SAME')
            self.d2_conv1 = nn.Conv2D (288, 288, kernel_size=3, strides=1, padding='SAME')

            self.d1_conv0 = nn.Conv2D (400, 160, kernel_size=3, strides=1, padding='SAME')
            self.d1_conv1 = nn.Conv2D (160, 160, kernel_size=3, strides=1, padding='SAME')

            self.d0_conv0 = nn.Conv2D (224, 96, kernel_size=3, strides=1, padding='SAME')
            self.d0_conv1 = nn.Conv2D (96, 96, kernel_size=3, strides=1, padding='SAME')

            self.out1x_conv0 = nn.Conv2D (96, 48, kernel_size=3, strides=1, padding='SAME')
            self.out1x_conv1 = nn.Conv2D (48, 3, kernel_size=3, strides=1, padding='SAME')

            self.dec2x_conv0 = nn.Conv2D (96, 96, kernel_size=3, strides=1, padding='SAME')
            self.dec2x_conv1 = nn.Conv2D (96, 96, kernel_size=3, strides=1, padding='SAME')

            self.out2x_conv0 = nn.Conv2D (96, 48, kernel_size=3, strides=1, padding='SAME')
            self.out2x_conv1 = nn.Conv2D (48, 3, kernel_size=3, strides=1, padding='SAME')

            self.dec4x_conv0 = nn.Conv2D (96, 72, kernel_size=3, strides=1, padding='SAME')
            self.dec4x_conv1 = nn.Conv2D (72, 72, kernel_size=3, strides=1, padding='SAME')

            self.out4x_conv0 = nn.Conv2D (72, 36, kernel_size=3, strides=1, padding='SAME')
            self.out4x_conv1 = nn.Conv2D (36, 3 , kernel_size=3, strides=1, padding='SAME')

        def forward(self, inp):
            bgr, param, param1 = inp

            x = self.conv1(bgr)
            a = self.dense1(param)
            a = tf.reshape(a, (-1,1,1,64) )

            b = self.dense2(param1)
            b = tf.reshape(b, (-1,1,1,64) )

            x = tf.nn.leaky_relu(x+a+b, 0.1)

            x = tf.nn.leaky_relu(self.e0_conv0(x), 0.1)
            x = e0 = tf.nn.leaky_relu(self.e0_conv1(x), 0.1)

            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], "VALID")
            x = tf.nn.leaky_relu(self.e1_conv0(x), 0.1)
            x = e1 = tf.nn.leaky_relu(self.e1_conv1(x), 0.1)

            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], "VALID")
            x = tf.nn.leaky_relu(self.e2_conv0(x), 0.1)
            x = e2 = tf.nn.leaky_relu(self.e2_conv1(x), 0.1)

            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], "VALID")
            x = tf.nn.leaky_relu(self.e3_conv0(x), 0.1)
            x = e3 = tf.nn.leaky_relu(self.e3_conv1(x), 0.1)

            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], "VALID")
            x = tf.nn.leaky_relu(self.e4_conv0(x), 0.1)
            x = e4 = tf.nn.leaky_relu(self.e4_conv1(x), 0.1)

            x = tf.nn.avg_pool(x, [1,2,2,1], [1,2,2,1], "VALID")
            x = tf.nn.leaky_relu(self.center_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.center_conv1(x), 0.1)
            x = tf.nn.leaky_relu(self.center_conv2(x), 0.1)
            x = tf.nn.leaky_relu(self.center_conv3(x), 0.1)

            x = tf.concat( [nn.tf_upsample2d_bilinear(x), e4], -1 )
            x = tf.nn.leaky_relu(self.d4_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.d4_conv1(x), 0.1)

            x = tf.concat( [nn.tf_upsample2d_bilinear(x), e3], -1 )
            x = tf.nn.leaky_relu(self.d3_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.d3_conv1(x), 0.1)

            x = tf.concat( [nn.tf_upsample2d_bilinear(x), e2], -1 )
            x = tf.nn.leaky_relu(self.d2_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.d2_conv1(x), 0.1)

            x = tf.concat( [nn.tf_upsample2d_bilinear(x), e1], -1 )
            x = tf.nn.leaky_relu(self.d1_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.d1_conv1(x), 0.1)

            x = tf.concat( [nn.tf_upsample2d_bilinear(x), e0], -1 )
            x = tf.nn.leaky_relu(self.d0_conv0(x), 0.1)
            x = d0 = tf.nn.leaky_relu(self.d0_conv1(x), 0.1)

            x = tf.nn.leaky_relu(self.out1x_conv0(x), 0.1)
            x = self.out1x_conv1(x)
            out1x = bgr + tf.nn.tanh(x)

            x = d0
            x = tf.nn.leaky_relu(self.dec2x_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.dec2x_conv1(x), 0.1)
            x = d2x = nn.tf_upsample2d_bilinear(x)

            x = tf.nn.leaky_relu(self.out2x_conv0(x), 0.1)
            x = self.out2x_conv1(x)

            out2x = nn.tf_upsample2d_bilinear(out1x) + tf.nn.tanh(x)

            x = d2x
            x = tf.nn.leaky_relu(self.dec4x_conv0(x), 0.1)
            x = tf.nn.leaky_relu(self.dec4x_conv1(x), 0.1)
            x = d4x = nn.tf_upsample2d_bilinear(x)

            x = tf.nn.leaky_relu(self.out4x_conv0(x), 0.1)
            x = self.out4x_conv1(x)

            out4x = nn.tf_upsample2d_bilinear(out2x) + tf.nn.tanh(x)

            return out4x


    with tf.device ("/CPU:0"):
        face_enhancer = FaceEnhancer()

        if True:
            face_enhancer.load_weights (r"D:\DevelopPython\test\FaceEnhancer.npy")

            face_enhancer.save_weights (r"D:\DevelopPython\test\FaceEnhancer.npy", np.float16)
            face_enhancer.load_weights (r"D:\DevelopPython\test\FaceEnhancer.npy")
        else:
            face_enhancer.build()
            face_enhancer.conv1.set_weights( [get_op_value('tl_unet1x2x4x/paramW'), get_op_value('tl_unet1x2x4x/paramB')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.dense1.set_weights( [get_op_value('tl_unet1x2x4x/paramInW')]  )
            face_enhancer.dense2.set_weights( [get_op_value('tl_unet1x2x4x/paramInW1')]  )

            face_enhancer.e0_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_0/w0'), get_op_value('tl_unet1x2x4x/Encoder_0/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e0_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_0/w1'), get_op_value('tl_unet1x2x4x/Encoder_0/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e1_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_1/w0'), get_op_value('tl_unet1x2x4x/Encoder_1/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e1_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_1/w1'), get_op_value('tl_unet1x2x4x/Encoder_1/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e2_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_2/w0'), get_op_value('tl_unet1x2x4x/Encoder_2/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e2_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_2/w1'), get_op_value('tl_unet1x2x4x/Encoder_2/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e3_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_3/w0'), get_op_value('tl_unet1x2x4x/Encoder_3/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e3_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_3/w1'), get_op_value('tl_unet1x2x4x/Encoder_3/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e4_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_4/w0'), get_op_value('tl_unet1x2x4x/Encoder_4/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.e4_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Encoder_4/w1'), get_op_value('tl_unet1x2x4x/Encoder_4/b1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.center_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Center/w0'), get_op_value('tl_unet1x2x4x/Center/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.center_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Center/w1'), get_op_value('tl_unet1x2x4x/Center/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.center_conv2.set_weights( [get_op_value('tl_unet1x2x4x/Center/w2'), get_op_value('tl_unet1x2x4x/Center/b2')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.center_conv3.set_weights( [get_op_value('tl_unet1x2x4x/Center/w3'), get_op_value('tl_unet1x2x4x/Center/b3')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.d4_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_4/w0'), get_op_value('tl_unet1x2x4x/Decoder_4/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d4_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_4/w1'), get_op_value('tl_unet1x2x4x/Decoder_4/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d3_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_3/w0'), get_op_value('tl_unet1x2x4x/Decoder_3/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d3_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_3/w1'), get_op_value('tl_unet1x2x4x/Decoder_3/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d2_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_2/w0'), get_op_value('tl_unet1x2x4x/Decoder_2/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d2_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_2/w1'), get_op_value('tl_unet1x2x4x/Decoder_2/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d1_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_1/w0'), get_op_value('tl_unet1x2x4x/Decoder_1/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d1_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_1/w1'), get_op_value('tl_unet1x2x4x/Decoder_1/b1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d0_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_0/w0'), get_op_value('tl_unet1x2x4x/Decoder_0/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.d0_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_0/w1'), get_op_value('tl_unet1x2x4x/Decoder_0/b1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.out1x_conv0.set_weights( [get_op_value('tl_unet1x2x4x/out1x/W0'), get_op_value('tl_unet1x2x4x/out1x/B0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.out1x_conv1.set_weights( [get_op_value('tl_unet1x2x4x/out1x/W1'), get_op_value('tl_unet1x2x4x/out1x/B1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.dec2x_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_2x/w0'), get_op_value('tl_unet1x2x4x/Decoder_2x/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.dec2x_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_2x/w1'), get_op_value('tl_unet1x2x4x/Decoder_2x/b1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.out2x_conv0.set_weights( [get_op_value('tl_unet1x2x4x/out2x/W0'), get_op_value('tl_unet1x2x4x/out2x/B0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.out2x_conv1.set_weights( [get_op_value('tl_unet1x2x4x/out2x/W1'), get_op_value('tl_unet1x2x4x/out2x/B1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.dec4x_conv0.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_4x/w0'), get_op_value('tl_unet1x2x4x/Decoder_4x/b0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.dec4x_conv1.set_weights( [get_op_value('tl_unet1x2x4x/Decoder_4x/w1'), get_op_value('tl_unet1x2x4x/Decoder_4x/b1')[0].reshape( (1,1,1,-1)) ] )

            face_enhancer.out4x_conv0.set_weights( [get_op_value('tl_unet1x2x4x/out4x/W0'), get_op_value('tl_unet1x2x4x/out4x/B0')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.out4x_conv1.set_weights( [get_op_value('tl_unet1x2x4x/out4x/W1'), get_op_value('tl_unet1x2x4x/out4x/B1')[0].reshape( (1,1,1,-1)) ] )
            face_enhancer.save_weights (r"D:\DevelopPython\test\FaceEnhancer.npy")


    #import code
    #code.interact(local=dict(globals(), **locals()))


    """
    x = Conv2D (64, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/paramW'), get_op_value('tl_unet1x2x4x/paramB')[0] ]  )(bgr_inp)

    a = Dense (64, use_bias=False, weights=[get_op_value('tl_unet1x2x4x/paramInW')] ) ( t_param_inp )
    a = Reshape( (1,1,64) )(a)
    b = Dense (64, use_bias=False, weights=[get_op_value('tl_unet1x2x4x/paramInW1')] ) ( t_param1_inp )
    b = Reshape( (1,1,64) )(b)
    x = Add()([x,a,b])

    x = LeakyReLU(0.1)(x)

    x = LeakyReLU(0.1)(Conv2D (64, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_0/w0'), get_op_value('tl_unet1x2x4x/Encoder_0/b0')[0] ]  )(x))
    x = e0 = LeakyReLU(0.1)(Conv2D (64, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_0/w1'), get_op_value('tl_unet1x2x4x/Encoder_0/b1')[0] ]  )(x))


    x = AveragePooling2D()(x)
    x = LeakyReLU(0.1)(Conv2D (112, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_1/w0'), get_op_value('tl_unet1x2x4x/Encoder_1/b0')[0] ]  )(x))
    x = e1 = LeakyReLU(0.1)(Conv2D (112, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_1/w1'), get_op_value('tl_unet1x2x4x/Encoder_1/b1')[0] ]  )(x))

    x = AveragePooling2D()(x)
    x = LeakyReLU(0.1)(Conv2D (192, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_2/w0'), get_op_value('tl_unet1x2x4x/Encoder_2/b0')[0] ]  )(x))
    x = e2 = LeakyReLU(0.1)(Conv2D (192, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_2/w1'), get_op_value('tl_unet1x2x4x/Encoder_2/b1')[0] ]  )(x))

    x = AveragePooling2D()(x)
    x = LeakyReLU(0.1)(Conv2D (336, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_3/w0'), get_op_value('tl_unet1x2x4x/Encoder_3/b0')[0] ]  )(x))
    x = e3 = LeakyReLU(0.1)(Conv2D (336, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_3/w1'), get_op_value('tl_unet1x2x4x/Encoder_3/b1')[0] ]  )(x))

    x = AveragePooling2D()(x)
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_4/w0'), get_op_value('tl_unet1x2x4x/Encoder_4/b0')[0] ]  )(x))
    x = e4 = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Encoder_4/w1'), get_op_value('tl_unet1x2x4x/Encoder_4/b1')[0] ]  )(x))

    x = AveragePooling2D()(x)
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Center/w0'), get_op_value('tl_unet1x2x4x/Center/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Center/w1'), get_op_value('tl_unet1x2x4x/Center/b1')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Center/w2'), get_op_value('tl_unet1x2x4x/Center/b2')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Center/w3'), get_op_value('tl_unet1x2x4x/Center/b3')[0] ]  )(x))


    x = Concatenate()([ BilinearInterpolation()(x), e4 ])


    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_4/w0'), get_op_value('tl_unet1x2x4x/Decoder_4/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_4/w1'), get_op_value('tl_unet1x2x4x/Decoder_4/b1')[0] ]  )(x))

    x = Concatenate()([ BilinearInterpolation()(x), e3 ])
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_3/w0'), get_op_value('tl_unet1x2x4x/Decoder_3/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (512, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_3/w1'), get_op_value('tl_unet1x2x4x/Decoder_3/b1')[0] ]  )(x))

    x = Concatenate()([ BilinearInterpolation()(x), e2 ])
    x = LeakyReLU(0.1)(Conv2D (288, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_2/w0'), get_op_value('tl_unet1x2x4x/Decoder_2/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (288, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_2/w1'), get_op_value('tl_unet1x2x4x/Decoder_2/b1')[0] ]  )(x))

    x = Concatenate()([ BilinearInterpolation()(x), e1 ])
    x = LeakyReLU(0.1)(Conv2D (160, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_1/w0'), get_op_value('tl_unet1x2x4x/Decoder_1/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (160, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_1/w1'), get_op_value('tl_unet1x2x4x/Decoder_1/b1')[0] ]  )(x))

    x = Concatenate()([ BilinearInterpolation()(x), e0 ])
    x = LeakyReLU(0.1)(Conv2D (96, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_0/w0'), get_op_value('tl_unet1x2x4x/Decoder_0/b0')[0] ]  )(x))
    x = d0 = LeakyReLU(0.1)(Conv2D (96, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_0/w1'), get_op_value('tl_unet1x2x4x/Decoder_0/b1')[0] ]  )(x))

    x = LeakyReLU(0.1)(Conv2D (48, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/out1x/W0'), get_op_value('tl_unet1x2x4x/out1x/B0')[0] ]  )(x))

    x = Conv2D (3, 3, strides=1, padding='same', activation='tanh', weights=[get_op_value('tl_unet1x2x4x/out1x/W1'), get_op_value('tl_unet1x2x4x/out1x/B1')[0] ]  )(x)
    out1x = Add()([bgr_inp, x])

    x = d0
    x = LeakyReLU(0.1)(Conv2D (96, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_2x/w0'), get_op_value('tl_unet1x2x4x/Decoder_2x/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (96, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_2x/w1'), get_op_value('tl_unet1x2x4x/Decoder_2x/b1')[0] ]  )(x))
    x = d2x = BilinearInterpolation()(x)

    x = LeakyReLU(0.1)(Conv2D (48, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/out2x/W0'), get_op_value('tl_unet1x2x4x/out2x/B0')[0] ]  )(x))
    x = Conv2D (3, 3, strides=1, padding='same', activation='tanh', weights=[get_op_value('tl_unet1x2x4x/out2x/W1'), get_op_value('tl_unet1x2x4x/out2x/B1')[0] ]  )(x)

    out2x = Add()([BilinearInterpolation()(out1x), x])

    x = d2x
    x = LeakyReLU(0.1)(Conv2D (72, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_4x/w0'), get_op_value('tl_unet1x2x4x/Decoder_4x/b0')[0] ]  )(x))
    x = LeakyReLU(0.1)(Conv2D (72, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/Decoder_4x/w1'), get_op_value('tl_unet1x2x4x/Decoder_4x/b1')[0] ]  )(x))
    x = d4x = BilinearInterpolation()(x)

    x = LeakyReLU(0.1)(Conv2D (36, 3, strides=1, padding='same', weights=[get_op_value('tl_unet1x2x4x/out4x/W0'), get_op_value('tl_unet1x2x4x/out4x/B0')[0] ]  )(x))
    x = Conv2D (3, 3, strides=1, padding='same', activation='tanh', weights=[get_op_value('tl_unet1x2x4x/out4x/W1'), get_op_value('tl_unet1x2x4x/out4x/B1')[0] ]  )(x)
    out4x = Add()([BilinearInterpolation()(out2x), x ])
    """

    #model = keras.models.Model ( [bgr_inp,t_param_inp,t_param1_inp], [out4x] )
    #model.load_weights (r"D:\DevelopPython\test\Jiva.h5")

    #weights_filepath = Path(r"D:\DevelopPython\test\FaceEnhancer.npy")
    #model.save_weights (str(weights_filepath))

    #weights_filepath
    #import code
    #code.interact(local=dict(globals(), **locals()))


    """


    param = np.array([0.2])
    param1 = np.array([1.0])

    up_res = 4
    patch_size = 192
    patch_size_half = patch_size // 2

    #inp_img = border_pad(inp_img, patch_size_half)
    h,w,c = inp_img.shape

    i_max = w-patch_size+1
    j_max = h-patch_size+1

    final_img = np.zeros ( (h*up_res,w*up_res,c), dtype=np.float32 )
    final_img_div = np.zeros ( (h*up_res,w*up_res,1), dtype=np.float32 )


    x = np.concatenate ( [ np.linspace (0,1,patch_size_half*up_res), np.linspace (1,0,patch_size_half*up_res) ] )
    x,y = np.meshgrid(x,x)
    patch_mask = (x*y)[...,None]

    j=0
    while j < j_max:
        i = 0
        while i < i_max:
            is_last = i == i_max-1

            patch_img = inp_img[j:j+patch_size, i:i+patch_size,:]

            x = model.predict( [ patch_img[None,...], param, param1 ] )[0]

            final_img    [j*up_res:(j+patch_size)*up_res, i*up_res:(i+patch_size)*up_res,:] += x*patch_mask
            final_img_div[j*up_res:(j+patch_size)*up_res, i*up_res:(i+patch_size)*up_res,:] += patch_mask

            if is_last:
                break

            i = min( i+patch_size_half, i_max-1)

        if j == j_max-1:
            break
        j = min( j+patch_size_half, j_max-1)

    final_img_div[final_img_div==0] = 1.0
    final_img /= final_img_div

    cv2.imshow("", ( np.clip( (final_img/2+0.5)*255, 0, 255) ).astype(np.uint8) )
    cv2.waitKey(0)
    """



    """
    def border_pad(x, pad):

        x = np.concatenate ([ np.tile(x[:,0:1,:], (1,pad,1) ),
                              x,
                              np.tile(x[:,-2:-1,:], (1,pad,1) ) ], axis=1 )

        x = np.concatenate ([ np.tile(x[0:1,:,:], (pad,1,1) ),
                              x,
                              np.tile(x[-2:-1,:,:], (pad,1,1) ) ], axis=0 )
        return x
    def reflect_pad(x, pad):
        x = np.concatenate ([ x[:,pad:0:-1,:],
                             x,
                             x[:,-2:-pad-2:-1,:] ], axis=1 )
        x = np.concatenate ([ x[pad:0:-1,:,:],
                             x,
                             x[-2:-pad-2:-1,:,:] ], axis=0 )
        return x


    psnr1 = K.placeholder( (None,None,None))
    psnr2 = K.placeholder( (None,None,None))
    psnr_func = K.function([psnr1, psnr2], [tf.image.psnr (psnr1, psnr2, max_val=2.0)])

    j=0
    while j < j_max:
        i = 0
        while i < i_max:
            is_first = i == 0
            is_last  = i == i_max-1

            pr=[]
            psnrs=[]

            mod = 1 if is_first else -1

            for n in range(n_psnr_patches):

                patch_img = inp_img[j:j+192, i+n*mod:i+n*mod+192,:]
                bilinear_patch_img = bilinear_img[j*4:(j+192)*4, (i+n*mod)*4:(i+n*mod+192)*4,:]

                x = model.predict( [ patch_img[None,...], param, param1 ] )[0]
                pr += [ x ]
                psnrs += [ psnr_func ( [x, bilinear_patch_img ])[0] ]

            final_img[j*4:(j+192)*4, i*4:(i+192)*4,:] = pr[0]

            best_n = np.argmin(np.array(psnrs) )
            if best_n != 0:
                final_img[j*4:(j+192)*4, (i+best_n*mod)*4:(i+best_n*mod+192)*4,:] = pr[best_n]

            if is_last:
                break

            i = min( best_n+192, i_max-1)

        if j == j_max-1:
            break
        j = min( j+192, j_max-1)
    """
    #patch_img = inp_img[j:j+192, i:i+192,:]

    #final_img[j*4:j*4+192*4, i*4:i*4+192*4,:] = img

    #x = model.predict( [ patch_img[None,...], param, param1 ] )



    #cv2.imshow("", ( np.clip( (img/2+0.5)*255, 0, 255) ).astype(np.uint8) )
    #cv2.waitKey(0)

    #blur = cv2.GaussianBlur(x, (3, 3), 0)
    #x = cv2.addWeighted(x, 1.0 + (0.5 * amount), blur, -(0.5 * amount), 0)
    #cv2.filter2D(x, -1, kernel)

    #final_img    [j*4:j*4+192*4, i*4:i*4+192*4,:] += img#np.clip(x/2+0.5,0, 1)
    #final_img_div[j*4:j*4+192*4, i*4:i*4+192*4,:] += 1.0

    #import code
    #code.interact(local=dict(globals(), **locals()))


    input = graph.get_tensor_by_name('netInput:0')
    t_param = graph.get_tensor_by_name('t_param:0')
    t_param1 = graph.get_tensor_by_name('t_param1:0')


    filepath =  r'D:\DevelopPython\test\00000.jpg'
    img = cv2.imread(filepath).astype(np.float32) / 255.0
    inp_img = img *2 - 1
    inp_img = cv2.resize (inp_img, (192,192) )

    """
    with tf.device ("/CPU:0"):
        face_enhancer = FaceEnhancer(name=f'fe')
        face_enhancer.load_weights (r"D:\DevelopPython\test\FaceEnhancer.npy")
        face_enhancer.build_for_run ([ (tf.float32, (192,192,3) ),
                            (tf.float32, (1,) ),
                            (tf.float32, (1,) ),
                          ])
    """
    #writer = tf.summary.FileWriter(r'D:\logs', sess.graph)



    face_enhancer.build_for_run ([ (tf.float32, (192,192,3) ),
                            (tf.float32, (1,) ),
                            (tf.float32, (1,) ),
                          ])
    param = 0.2
    param1 = 1.0
    inp_x = 0
    while True:
        #inp_img = img[-192:,inp_x:inp_x+192,:]
        #inp_img = img[inp_x:inp_x+192,-192:,:]
        #inp_img = img[-192:,-192:,:]

        #output = graph.get_tensor_by_name('tl_unet1x2x4x/out1x/Tanh:0')
        output = graph.get_tensor_by_name('netOutput4X:0')
        #output = graph.get_tensor_by_name('tl_unet1x2x4x/Conv2D:0')

        x1 = sess.run (output, feed_dict={input: inp_img[None,...],
                            t_param: np.array([param]),
                            t_param1: np.array([param1])  } )

        #x = face_enhancer_predict( inp_img[None,...], np.array([[param]]), np.array([[param1]]) )


        x = face_enhancer.run ([ inp_img[None,...], np.array([[param]]), np.array([[param1]]) ])

        print (f"diff = {np.sum(np.abs(x1-x))}")
        import code
        code.interact(local=dict(globals(), **locals()))




        x1 = np.clip( x1/2 + 0.5, 0, 1)
        cv2.imshow("", (x1[0]*255).astype(np.uint8) )
        cv2.waitKey(0)

        x = np.clip( x/2 + 0.5, 0, 1)
        cv2.imshow("", (x[0]*255).astype(np.uint8) )
        cv2.waitKey(0)

        #param += 0.1
        #inp_x += 1


    #[n.name for n in tf.get_default_graph().as_graph_def().node]

    ct_1_filepath =  r'D:\DevelopPython\test\00000.jpg'#r'F:\DeepFaceLabCUDA9.2SSE\workspace\data_dst\aligned\00658_0.jpg'
    ct_1_img = cv2.imread(ct_1_filepath).astype(np.float32) / 255.0
    ct_1_img_shape = ct_1_img.shape
    ct_1_dflimg = DFLJPG.load ( ct_1_filepath)

    ct_1_mask = LandmarksProcessor.get_image_hull_mask (ct_1_img_shape , ct_1_dflimg.get_landmarks() )

    img_size = 128
    face_mat = LandmarksProcessor.get_transform_mat( ct_1_dflimg.get_landmarks(), img_size, FaceType.FULL, scale=1.0)
    wrp = cv2.warpAffine(ct_1_img, face_mat, (img_size, img_size), cv2.INTER_LANCZOS4)


    cv2.imshow("", (wrp*255).astype(np.uint8) )
    cv2.waitKey(0)

    #=====================================



    def np_gen_ca(shape, dtype=np.float32, eps_std=0.05):
        """
        Super fast implementation of Convolution Aware Initialization for 4D shapes
        Convolution Aware Initialization https://arxiv.org/abs/1702.06295
        """
        if len(shape) != 4:
            raise ValueError("only shape with rank 4 supported.")

        row, column, stack_size, filters_size = shape

        fan_in = stack_size * (row * column)

        kernel_shape = (row, column)

        kernel_fft_shape = np.fft.rfft2(np.zeros(kernel_shape)).shape

        basis_size = np.prod(kernel_fft_shape)
        if basis_size == 1:
            x = np.random.normal( 0.0, eps_std, (filters_size, stack_size, basis_size) ).astype(dtype)
        else:
            nbb = stack_size // basis_size + 1

            x = np.random.normal(0.0, 1.0, (filters_size, nbb, basis_size, basis_size)).astype(dtype)

            x = x + np.transpose(x, (0,1,3,2) ) * (1-np.eye(basis_size))

            u, _, v = np.linalg.svd(x)
            x = np.transpose(u, (0,1,3,2) )

            x = np.reshape(x, (filters_size, -1, basis_size) )
            x = x[:,:stack_size,:]

        x = np.reshape(x, ( (filters_size,stack_size,) + kernel_fft_shape ) )

        x = np.fft.irfft2( x, kernel_shape ) \
            + np.random.normal(0, eps_std, (filters_size,stack_size,)+kernel_shape).astype(dtype)

        x = x * np.sqrt( (2/fan_in) / np.var(x) )
        x = np.transpose( x, (2, 3, 1, 0) )
        return x

    from core.leras import nn
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf
    from tensorflow.python.ops import init_ops

    class CAInitializer (init_ops.Initializer):
        def __init__(self, eps_std=0.05):
            self.eps_std = eps_std

        def gen_ca_4d_func(self, dtype=np.float32):

            def func(shape):
                """
                Super fast implementation of Convolution Aware Initialization for 4D shapes
                Convolution Aware Initialization https://arxiv.org/abs/1702.06295
                """
                if len(shape) != 4:
                    raise ValueError("only shape with rank 4 supported.")

                row, column, stack_size, filters_size = shape

                fan_in = stack_size * (row * column)

                kernel_shape = (row, column)

                kernel_fft_shape = np.fft.rfft2(np.zeros(kernel_shape)).shape

                basis_size = np.prod(kernel_fft_shape)
                if basis_size == 1:
                    x = np.random.normal( 0.0, self.eps_std, (filters_size, stack_size, basis_size) )
                else:
                    nbb = stack_size // basis_size + 1
                    x = np.random.normal(0.0, 1.0, (filters_size, nbb, basis_size, basis_size))
                    x = x + np.transpose(x, (0,1,3,2) ) * (1-np.eye(basis_size))
                    u, _, v = np.linalg.svd(x)
                    x = np.transpose(u, (0,1,3,2) )
                    x = np.reshape(x, (filters_size, -1, basis_size) )
                    x = x[:,:stack_size,:]

                x = np.reshape(x, ( (filters_size,stack_size,) + kernel_fft_shape ) )

                x = np.fft.irfft2( x, kernel_shape ) \
                    + np.random.normal(0, self.eps_std, (filters_size,stack_size,)+kernel_shape)

                x = x * np.sqrt( (2/fan_in) / np.var(x) )
                x = np.transpose( x, (2, 3, 1, 0) )
                return x.astype(dtype)
            return func

        def __call__(self, shape, dtype=None, partition_info=None):
            return tf.py_func( self.gen_ca_4d_func(dtype.as_numpy_dtype), [shape], dtype )

            import code
            code.interact(local=dict(globals(), **locals()))


    op = CAInitializer()( (3,3,128,128), tf.float32 )
    tf_ca = nn.tf_sess.run(op)

    import code
    code.interact(local=dict(globals(), **locals()))

    shape = (1,1,1024,1024)

    #t = time.time()
    #np_ca = CAGenerateWeights(shape, np.float32, 'channels_last', eps_std=0.05)
    #print(f"time = {time.time() -t}")

    t = time.time()
    np_ca2 = np_gen_ca(shape, np.float32, eps_std=0.05)
    print(f"time = {time.time() -t}")

     #input = tf.placeholder(tf.float32, (4,) )



    #y = tf.py_func(my_func, [input], tf.float32)


    #import code
    #code.interact(local=dict(globals(), **locals()))

    #with tf.device("/GPU:0"):





    from core.leras import nn
    nn.initialize( device_config=nn.DeviceConfig.WorstGPU() )
    tf = nn.tf

    shape = (3,3,64,128)

    fan_in = shape[-2] * np.prod( shape[:-2] )
    fan_out = shape[-1] * np.prod( shape[:-2] )
    variance = 2 / fan_in

    row, column, in_ch, out_ch = shape

    transpose_dimensions = (2, 3, 1, 0)
    kernel_shape = (row, column)
    correct_ifft = np.fft.irfft2
    correct_fft = np.fft.rfft2

    eps_std = 0.05
    floatx = np.float32


    """

    a = np.array ( [   [ [1,2], [3,4] ],
                       [ [1,2], [3,4] ],
                       [ [1,2], [3,4] ],
                       [ [1,2], [3,4] ]
                   ])
    import code
    code.interact(local=dict(globals(), **locals()))

    x, = nn.tf_sess.run( [ tf.spectral.rfft2d( tf.ones( (3,3) ) ) ] )

    a = np.array( [ np.complex64(v.real) for v in np.ndarray.flatten(x) ] ).reshape (x.shape)
    a_r = np.array( [v.real for v in np.ndarray.flatten(x) ] ).reshape (x.shape)

    a_p = tf.placeholder ( tf.complex64, (3,2) )

    y, = nn.tf_sess.run( [ tf.spectral.irfft2d(a_p) ], feed_dict={a_p:a} )

    import code
    code.interact(local=dict(globals(), **locals()))
    """
    """
    import code
    code.interact(local=dict(globals(), **locals()))

    for i in range(nbb):
        a = tf.random.normal( (size, size), 0.0, 1.0,  dtype=dtype  )
        a = a + tf.transpose(a) - tf.linalg.diag(tf.linalg.diag_part(a))







        s, u, v = tf.linalg.svd(a)

        import code
        code.interact(local=dict(globals(), **locals()))

        li.append ( tf.transpose(u) )

    return tf.concat(li, 0)[:filters, :]
    """


    from tensorflow.python.ops import init_ops

    class ConvolutionAwareInitializer(init_ops.Initializer):
        """
        Tensorflow initializer implementation of Convolution Aware Initialization
        https://arxiv.org/pdf/1702.06295.pdf
        """
        def __init__(self, eps_std=0.05):
            self.eps_std = eps_std

        def __call__(self, shape, dtype=tf.float32):
            if len(shape) != 4:
                raise ValueError("only shape with rank 4 supported.")

            row, column, stack_size, filters_size = shape

            fan_in = stack_size * (row * column)

            kernel_shape = (row, column)

            kernel_fft_shape = np.fft.rfft2(np.zeros(kernel_shape)).shape

            basis_size = np.prod(kernel_fft_shape)
            if basis_size == 1:
                x = tf.random.normal( (filters_size, stack_size, basis_size), 0.0, self.eps_std, dtype=dtype  )
            else:
                nbb = stack_size // basis_size + 1

                x = tf.random.normal( (filters_size, nbb, basis_size, basis_size), 0.0, 1.0,  dtype=dtype  )
                x = x + tf.transpose(x, (0,1,3,2) ) - tf.linalg.diag(tf.linalg.diag_part(x))
                s, u, v = tf.linalg.svd(x)
                x = tf.transpose(u, (0,1,3,2) )

                x = tf.reshape(x, (filters_size, -1, basis_size) )
                x = x[:,:stack_size,:]

            x = tf.reshape(x, ( (filters_size,stack_size,) + kernel_fft_shape ) )

            x = tf.spectral.irfft2d( tf.complex(x, tf.zeros_like(x) ), kernel_shape ) \
                + tf.random.normal( (filters_size,stack_size,)+kernel_shape, 0, self.eps_std)

            x_variance = tf.reduce_mean( tf.square(x - tf.reduce_mean(x,  keepdims=True) ) )

            x = x * tf.sqrt( (2/fan_in) / x_variance )
            x = tf.transpose( x, (2, 3, 1, 0) )
            return x

            import code
            code.interact(local=dict(globals(), **locals()))





            #return array_ops.ones(shape, dtype)


    np_ca = CAGenerateWeights(shape, np.float32, 'channels_last', eps_std=0.05)


    #input = tf.placeholder(tf.float32, (4,) )

    def my_func():
        pass

    #y = tf.py_func(my_func, [input], tf.float32)


    #import code
    #code.interact(local=dict(globals(), **locals()))

    #with tf.device("/GPU:0"):
    #tf_op = ConvolutionAwareInitializer()(shape)

    t = time.time()
    tf_ca = nn.tf_sess.run ([tf_op,tf_op2,tf_op3,tf_op4])
    print(f"time {time.time() - t}")

    import code
    code.interact(local=dict(globals(), **locals()))


    #=====================================


    #======================================



    import code
    code.interact(local=dict(globals(), **locals()))







    #=============================================

    from core.leras import nn
    nn.initialize( device_config=nn.DeviceConfig.GPUIndexes([1]) )
    tf = nn.tf

    import torch
    import torch.nn as tnn
    import torch.nn.functional as F


    def sf3d_keras(input_shape, sf3d_torch):

        inp = Input ( (None, None,3), dtype=K.floatx() )
        x = inp
        x = Lambda ( lambda x: x - K.constant([104,117,123]), output_shape=(None,None,3) ) (x)

        x = Conv2D(64, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv1_1), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(64, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv1_2), activation='relu') (ZeroPadding2D(1)(x))
        x = MaxPooling2D()(x)

        x = Conv2D(128, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv2_1), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(128, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv2_2), activation='relu') (ZeroPadding2D(1)(x))
        x = MaxPooling2D()(x)

        x = Conv2D(256, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv3_1), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(256, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv3_2), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(256, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv3_3), activation='relu') (ZeroPadding2D(1)(x))
        f3_3 = x
        x = MaxPooling2D()(x)

        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv4_1), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv4_2), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv4_3), activation='relu') (ZeroPadding2D(1)(x))
        f4_3 = x
        x = MaxPooling2D()(x)

        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv5_1), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv5_2), activation='relu') (ZeroPadding2D(1)(x))
        x = Conv2D(512, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv5_3), activation='relu') (ZeroPadding2D(1)(x))
        f5_3 = x
        x = MaxPooling2D()(x)

        x = ZeroPadding2D(padding=(3,3))(x)
        x = Conv2D(1024, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.fc6), activation='relu') (x)
        x = Conv2D(1024, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.fc7), activation='relu') (x)
        ffc7 = x

        x = Conv2D(256, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv6_1), activation='relu') (x)
        x = ZeroPadding2D(padding=(1,1))(x)
        x = Conv2D(512, kernel_size=3, strides=2, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv6_2), activation='relu') (x)
        f6_2 = x

        x = Conv2D(128, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv7_1), activation='relu') (x)
        x = ZeroPadding2D(padding=(1,1))(x)
        x = Conv2D(256, kernel_size=3, strides=2, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv7_2), activation='relu') (x)
        f7_2 = x

        class L2Norm(KL.Layer):
            def __init__(self, n_channels, scale=1.0, weights=None, **kwargs):
                self.n_channels = n_channels
                self.scale = scale

                self.weights_ = weights
                super(L2Norm, self).__init__(**kwargs)

            def build(self, input_shape):
                self.input_spec = None

                self.w = self.add_weight( shape=(1, 1, self.n_channels), initializer='ones', name='w' )

                if self.weights_ is not None:
                    self.set_weights( [self.weights_.reshape ( (1,1,-1) )] )

                self.built = True

            def call(self, inputs, training=None):
                x = inputs
                x = x / (K.sqrt( K.sum( K.pow(x, 2), axis=-1, keepdims=True ) ) + 1e-10) * self.w
                return x

            def get_config(self):
                config = {'n_channels': self.n_channels, 'scale': self.scale }

                base_config = super(L2Norm, self).get_config()
                return dict(list(base_config.items()) + list(config.items()))

            def compute_output_shape(self, input_shape):
                return input_shape

        f3_3 = L2Norm(256, scale=10, weights=sf3d_torch.conv3_3_norm.weight.data.cpu().numpy())(f3_3)
        f4_3 = L2Norm(512, scale=8, weights=sf3d_torch.conv4_3_norm.weight.data.cpu().numpy())(f4_3)
        f5_3 = L2Norm(512, scale=5, weights=sf3d_torch.conv5_3_norm.weight.data.cpu().numpy())(f5_3)

        cls1 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv3_3_norm_mbox_conf), activation='softmax')(ZeroPadding2D(1)(f3_3))
        reg1 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv3_3_norm_mbox_loc)) (ZeroPadding2D(1)(f3_3))

        cls2 = Conv2D(2, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv4_3_norm_mbox_conf), activation='softmax')(ZeroPadding2D(1)(f4_3))
        reg2 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv4_3_norm_mbox_loc)) (ZeroPadding2D(1)(f4_3))

        cls3 = Conv2D(2, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv5_3_norm_mbox_conf), activation='softmax')(ZeroPadding2D(1)(f5_3))
        reg3 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv5_3_norm_mbox_loc)) (ZeroPadding2D(1)(f5_3))

        cls4 = Conv2D(2, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.fc7_mbox_conf), activation='softmax')(ZeroPadding2D(1)(ffc7))
        reg4 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.fc7_mbox_loc)) (ZeroPadding2D(1)(ffc7))

        cls5 = Conv2D(2, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv6_2_mbox_conf), activation='softmax')(ZeroPadding2D(1)(f6_2))
        reg5 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv6_2_mbox_loc)) (ZeroPadding2D(1)(f6_2))

        cls6 = Conv2D(2, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv7_2_mbox_conf), activation='softmax')(ZeroPadding2D(1)(f7_2))
        reg6 = Conv2D(4, kernel_size=3, strides=1, padding='valid', weights=t2kw_conv2d(sf3d_torch.conv7_2_mbox_loc)) (ZeroPadding2D(1)(f7_2))

        L = Lambda ( lambda x: x[:,:,:,-1], output_shape=(None,None,1) )
        cls1, cls2, cls3, cls4, cls5, cls6 = [ L(x) for x in [cls1, cls2, cls3, cls4, cls5, cls6] ]

        return Model(inp, [cls1, reg1, cls2, reg2, cls3, reg3, cls4, reg4, cls5, reg5, cls6, reg6])

    class TL2Norm(tnn.Module):
        def __init__(self, n_channels, scale=1.0):
            super(TL2Norm, self).__init__()
            self.n_channels = n_channels
            self.scale = scale
            self.eps = 1e-10
            self.weight = tnn.Parameter(torch.Tensor(self.n_channels))
            self.weight.data *= 0.0
            self.weight.data += self.scale

        def forward(self, x):
            norm = x.pow(2).sum(dim=1, keepdim=True).sqrt() + self.eps
            x = x / norm * self.weight.view(1, -1, 1, 1)
            return x


    class s3fd_torch(tnn.Module):
        def __init__(self):
            super(s3fd_torch, self).__init__()
            self.conv1_1 = tnn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1)
            self.conv1_2 = tnn.Conv2d(64, 64, kernel_size=3, stride=1, padding=1)

            self.conv2_1 = tnn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1)
            self.conv2_2 = tnn.Conv2d(128, 128, kernel_size=3, stride=1, padding=1)

            self.conv3_1 = tnn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1)
            self.conv3_2 = tnn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1)
            self.conv3_3 = tnn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1)

            self.conv4_1 = tnn.Conv2d(256, 512, kernel_size=3, stride=1, padding=1)
            self.conv4_2 = tnn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1)
            self.conv4_3 = tnn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1)

            self.conv5_1 = tnn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1)
            self.conv5_2 = tnn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1)
            self.conv5_3 = tnn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1)

            self.fc6 = tnn.Conv2d(512, 1024, kernel_size=3, stride=1, padding=3)
            self.fc7 = tnn.Conv2d(1024, 1024, kernel_size=1, stride=1, padding=0)

            self.conv6_1 = tnn.Conv2d(1024, 256, kernel_size=1, stride=1, padding=0)
            self.conv6_2 = tnn.Conv2d(256, 512, kernel_size=3, stride=2, padding=1)

            self.conv7_1 = tnn.Conv2d(512, 128, kernel_size=1, stride=1, padding=0)
            self.conv7_2 = tnn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1)

            self.conv3_3_norm = TL2Norm(256, scale=10)
            self.conv4_3_norm = TL2Norm(512, scale=8)
            self.conv5_3_norm = TL2Norm(512, scale=5)

            self.conv3_3_norm_mbox_conf = tnn.Conv2d(256, 4, kernel_size=3, stride=1, padding=1)
            self.conv3_3_norm_mbox_loc = tnn.Conv2d(256, 4, kernel_size=3, stride=1, padding=1)
            self.conv4_3_norm_mbox_conf = tnn.Conv2d(512, 2, kernel_size=3, stride=1, padding=1)
            self.conv4_3_norm_mbox_loc = tnn.Conv2d(512, 4, kernel_size=3, stride=1, padding=1)
            self.conv5_3_norm_mbox_conf = tnn.Conv2d(512, 2, kernel_size=3, stride=1, padding=1)
            self.conv5_3_norm_mbox_loc = tnn.Conv2d(512, 4, kernel_size=3, stride=1, padding=1)

            self.fc7_mbox_conf = tnn.Conv2d(1024, 2, kernel_size=3, stride=1, padding=1)
            self.fc7_mbox_loc = tnn.Conv2d(1024, 4, kernel_size=3, stride=1, padding=1)
            self.conv6_2_mbox_conf = tnn.Conv2d(512, 2, kernel_size=3, stride=1, padding=1)
            self.conv6_2_mbox_loc = tnn.Conv2d(512, 4, kernel_size=3, stride=1, padding=1)
            self.conv7_2_mbox_conf = tnn.Conv2d(256, 2, kernel_size=3, stride=1, padding=1)
            self.conv7_2_mbox_loc = tnn.Conv2d(256, 4, kernel_size=3, stride=1, padding=1)

        def forward(self, x):

            h = F.relu(self.conv1_1(x))
            h = F.relu(self.conv1_2(h))
            h = F.max_pool2d(h, 2, 2)

            h = F.relu(self.conv2_1(h))
            h = F.relu(self.conv2_2(h))
            h = F.max_pool2d(h, 2, 2)

            h = F.relu(self.conv3_1(h))
            h = F.relu(self.conv3_2(h))
            h = F.relu(self.conv3_3(h))
            f3_3 = h
            h = F.max_pool2d(h, 2, 2)

            h = F.relu(self.conv4_1(h))
            h = F.relu(self.conv4_2(h))
            h = F.relu(self.conv4_3(h))
            f4_3 = h
            h = F.max_pool2d(h, 2, 2)

            h = F.relu(self.conv5_1(h))
            h = F.relu(self.conv5_2(h))
            h = F.relu(self.conv5_3(h))
            f5_3 = h
            h = F.max_pool2d(h, 2, 2)

            h = F.relu(self.fc6(h))
            h = F.relu(self.fc7(h))
            ffc7 = h

            h = F.relu(self.conv6_1(h))

            h = F.relu(self.conv6_2(h))

            f6_2 = h

            h = F.relu(self.conv7_1(h))
            h = F.relu(self.conv7_2(h))
            f7_2 = h


            f3_3 = self.conv3_3_norm(f3_3)
            f4_3 = self.conv4_3_norm(f4_3)
            f5_3 = self.conv5_3_norm(f5_3)

            cls1 = self.conv3_3_norm_mbox_conf(f3_3)
            reg1 = self.conv3_3_norm_mbox_loc(f3_3)
            cls2 = self.conv4_3_norm_mbox_conf(f4_3)
            reg2 = self.conv4_3_norm_mbox_loc(f4_3)
            cls3 = self.conv5_3_norm_mbox_conf(f5_3)
            reg3 = self.conv5_3_norm_mbox_loc(f5_3)

            cls4 = self.fc7_mbox_conf(ffc7)
            reg4 = self.fc7_mbox_loc(ffc7)
            cls5 = self.conv6_2_mbox_conf(f6_2)
            reg5 = self.conv6_2_mbox_loc(f6_2)
            cls6 = self.conv7_2_mbox_conf(f7_2)
            reg6 = self.conv7_2_mbox_loc(f7_2)

            # max-out background label
            chunk = torch.chunk(cls1, 4, 1)
            bmax = torch.max(torch.max(chunk[0], chunk[1]), chunk[2])
            cls1 = torch.cat ([bmax,chunk[3]], dim=1)
            cls1, cls2, cls3, cls4, cls5, cls6 = [ F.softmax(x, dim=1) for x in [cls1, cls2, cls3, cls4, cls5, cls6] ]
            return [cls1, reg1, cls2, reg2, cls3, reg3, cls4, reg4, cls5, reg5, cls6, reg6]


    class L2Norm(nn.LayerBase):
        def __init__(self, n_channels, **kwargs):
            self.n_channels = n_channels
            super().__init__(**kwargs)

        def init_weights(self):
            self.weight = tf.get_variable ("weight", (1, 1, 1, self.n_channels), dtype=nn.floatx, initializer=tf.initializers.ones )

        def get_weights(self):
            return [self.weight]

        def __call__(self, inputs):
            x = inputs
            x = x / (tf.sqrt( tf.reduce_sum( tf.pow(x, 2), axis=-1, keepdims=True ) ) + 1e-10) * self.weight
            return x

    class S3FD(nn.ModelBase):
        def __init__(self):
            super().__init__(name='S3FD')

        def on_build(self):
            self.minus = tf.constant([104,117,123], dtype=nn.floatx )
            self.conv1_1 = nn.Conv2D(3, 64, kernel_size=3, strides=1, padding='SAME')
            self.conv1_2 = nn.Conv2D(64, 64, kernel_size=3, strides=1, padding='SAME')

            self.conv2_1 = nn.Conv2D(64, 128, kernel_size=3, strides=1, padding='SAME')
            self.conv2_2 = nn.Conv2D(128, 128, kernel_size=3, strides=1, padding='SAME')

            self.conv3_1 = nn.Conv2D(128, 256, kernel_size=3, strides=1, padding='SAME')
            self.conv3_2 = nn.Conv2D(256, 256, kernel_size=3, strides=1, padding='SAME')
            self.conv3_3 = nn.Conv2D(256, 256, kernel_size=3, strides=1, padding='SAME')

            self.conv4_1 = nn.Conv2D(256, 512, kernel_size=3, strides=1, padding='SAME')
            self.conv4_2 = nn.Conv2D(512, 512, kernel_size=3, strides=1, padding='SAME')
            self.conv4_3 = nn.Conv2D(512, 512, kernel_size=3, strides=1, padding='SAME')

            self.conv5_1 = nn.Conv2D(512, 512, kernel_size=3, strides=1, padding='SAME')
            self.conv5_2 = nn.Conv2D(512, 512, kernel_size=3, strides=1, padding='SAME')
            self.conv5_3 = nn.Conv2D(512, 512, kernel_size=3, strides=1, padding='SAME')

            self.fc6 = nn.Conv2D(512, 1024, kernel_size=3, strides=1, padding=3)
            self.fc7 = nn.Conv2D(1024, 1024, kernel_size=1, strides=1, padding='SAME')

            self.conv6_1 = nn.Conv2D(1024, 256, kernel_size=1, strides=1, padding='SAME')
            self.conv6_2 = nn.Conv2D(256, 512, kernel_size=3, strides=2, padding='SAME')

            self.conv7_1 = nn.Conv2D(512, 128, kernel_size=1, strides=1, padding='SAME')
            self.conv7_2 = nn.Conv2D(128, 256, kernel_size=3, strides=2, padding='SAME')

            self.conv3_3_norm = L2Norm(256)
            self.conv4_3_norm = L2Norm(512)
            self.conv5_3_norm = L2Norm(512)


            self.conv3_3_norm_mbox_conf = nn.Conv2D(256, 4, kernel_size=3, strides=1, padding='SAME')
            self.conv3_3_norm_mbox_loc = nn.Conv2D(256, 4, kernel_size=3, strides=1, padding='SAME')

            self.conv4_3_norm_mbox_conf = nn.Conv2D(512, 2, kernel_size=3, strides=1, padding='SAME')
            self.conv4_3_norm_mbox_loc = nn.Conv2D(512, 4, kernel_size=3, strides=1, padding='SAME')

            self.conv5_3_norm_mbox_conf = nn.Conv2D(512, 2, kernel_size=3, strides=1, padding='SAME')
            self.conv5_3_norm_mbox_loc = nn.Conv2D(512, 4, kernel_size=3, strides=1, padding='SAME')

            self.fc7_mbox_conf = nn.Conv2D(1024, 2, kernel_size=3, strides=1, padding='SAME')
            self.fc7_mbox_loc = nn.Conv2D(1024, 4, kernel_size=3, strides=1, padding='SAME')

            self.conv6_2_mbox_conf = nn.Conv2D(512, 2, kernel_size=3, strides=1, padding='SAME')
            self.conv6_2_mbox_loc = nn.Conv2D(512, 4, kernel_size=3, strides=1, padding='SAME')

            self.conv7_2_mbox_conf = nn.Conv2D(256, 2, kernel_size=3, strides=1, padding='SAME')
            self.conv7_2_mbox_loc = nn.Conv2D(256, 4, kernel_size=3, strides=1, padding='SAME')

        def call(self, x):
            x = x - self.minus
            x = tf.nn.relu(self.conv1_1(x))
            x = tf.nn.relu(self.conv1_2(x))
            x = tf.nn.max_pool(x, [1,2,2,1], [1,2,2,1], "VALID")

            x = tf.nn.relu(self.conv2_1(x))
            x = tf.nn.relu(self.conv2_2(x))
            x = tf.nn.max_pool(x, [1,2,2,1], [1,2,2,1], "VALID")

            x = tf.nn.relu(self.conv3_1(x))
            x = tf.nn.relu(self.conv3_2(x))
            x = tf.nn.relu(self.conv3_3(x))
            f3_3 = x
            x = tf.nn.max_pool(x, [1,2,2,1], [1,2,2,1], "VALID")

            x = tf.nn.relu(self.conv4_1(x))
            x = tf.nn.relu(self.conv4_2(x))
            x = tf.nn.relu(self.conv4_3(x))
            f4_3 = x
            x = tf.nn.max_pool(x, [1,2,2,1], [1,2,2,1], "VALID")

            x = tf.nn.relu(self.conv5_1(x))
            x = tf.nn.relu(self.conv5_2(x))
            x = tf.nn.relu(self.conv5_3(x))
            f5_3 = x
            x = tf.nn.max_pool(x, [1,2,2,1], [1,2,2,1], "VALID")

            x = tf.nn.relu(self.fc6(x))
            x = tf.nn.relu(self.fc7(x))
            ffc7 = x

            x = tf.nn.relu(self.conv6_1(x))
            x = tf.nn.relu(self.conv6_2(x))
            f6_2 = x

            x = tf.nn.relu(self.conv7_1(x))
            x = tf.nn.relu(self.conv7_2(x))
            f7_2 = x

            f3_3 = self.conv3_3_norm(f3_3)
            f4_3 = self.conv4_3_norm(f4_3)
            f5_3 = self.conv5_3_norm(f5_3)

            cls1 = self.conv3_3_norm_mbox_conf(f3_3)
            reg1 = self.conv3_3_norm_mbox_loc(f3_3)

            cls2 = tf.nn.softmax(self.conv4_3_norm_mbox_conf(f4_3))
            reg2 = self.conv4_3_norm_mbox_loc(f4_3)

            cls3 = tf.nn.softmax(self.conv5_3_norm_mbox_conf(f5_3))
            reg3 = self.conv5_3_norm_mbox_loc(f5_3)

            cls4 = tf.nn.softmax(self.fc7_mbox_conf(ffc7))
            reg4 = self.fc7_mbox_loc(ffc7)

            cls5 = tf.nn.softmax(self.conv6_2_mbox_conf(f6_2))
            reg5 = self.conv6_2_mbox_loc(f6_2)

            cls6 = tf.nn.softmax(self.conv7_2_mbox_conf(f7_2))
            reg6 = self.conv7_2_mbox_loc(f7_2)

            # max-out background label
            bmax = tf.maximum(tf.maximum(cls1[:,:,:,0:1], cls1[:,:,:,1:2]), cls1[:,:,:,2:3])

            cls1 = tf.concat ([bmax, cls1[:,:,:,3:4] ], axis=-1)
            cls1 = tf.nn.softmax(cls1)

            return [cls1, reg1, cls2, reg2, cls3, reg3, cls4, reg4, cls5, reg5, cls6, reg6]


    model_path = r"D:\DevelopPython\test\s3fd.pth"
    model_weights = torch.load(str(model_path))

    device = 'cpu'
    fd_torch = s3fd_torch()

    fd_torch.load_state_dict(model_weights)
    fd_torch.eval()

    def decode(loc, priors, variances):
        boxes = np.concatenate((priors[:, :2] + loc[:, :2] * variances[0] * priors[:, 2:],
                                priors[:, 2:] * np.exp(loc[:, 2:] * variances[1])),
                               1)
        boxes[:, :2] -= boxes[:, 2:] / 2
        boxes[:, 2:] += boxes[:, :2]
        return boxes

    def softmax(x, axis=-1):
        y = np.exp(x - np.max(x, axis, keepdims=True))
        return y / np.sum(y, axis, keepdims=True)

    def nms(dets, thresh):
        """ Perform Non-Maximum Suppression """
        keep = list()
        if len(dets) == 0:
            return keep

        x_1, y_1, x_2, y_2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
        areas = (x_2 - x_1 + 1) * (y_2 - y_1 + 1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx_1, yy_1 = np.maximum(x_1[i], x_1[order[1:]]), np.maximum(y_1[i], y_1[order[1:]])
            xx_2, yy_2 = np.minimum(x_2[i], x_2[order[1:]]), np.minimum(y_2[i], y_2[order[1:]])

            width, height = np.maximum(0.0, xx_2 - xx_1 + 1), np.maximum(0.0, yy_2 - yy_1 + 1)
            ovr = width * height / (areas[i] + areas[order[1:]] - width * height)

            inds = np.where(ovr <= thresh)[0]
            order = order[inds + 1]
        return keep

    def detect_torch(olist):

        bboxlist = []

        for i in range(len(olist) // 2):
            ocls, oreg = olist[i * 2], olist[i * 2 + 1]
            stride = 2**(i + 2)    # 4,8,16,32,64,128
            poss = [*zip(*np.where(ocls[:, 1, :, :] > 0.05))]

            #import code
            #code.interact(local=dict(globals(), **locals()))

            for Iindex, hindex, windex in poss:
                axc, ayc = stride / 2 + windex * stride, stride / 2 + hindex * stride
                score = ocls[0, 1, hindex, windex]
                loc = np.ascontiguousarray(oreg[0, :, hindex, windex]).reshape((1, 4))
                priors = np.array([[axc / 1.0, ayc / 1.0, stride * 4 / 1.0, stride * 4 / 1.0]])
                variances = [0.1, 0.2]
                box = decode(loc, priors, variances)
                x1, y1, x2, y2 = box[0] * 1.0
                bboxlist.append([x1, y1, x2, y2, score])
        bboxlist = np.array(bboxlist)
        if 0 == len(bboxlist):
            bboxlist = np.zeros((1, 5))

        return bboxlist

    def detect_keras(olist):
        bboxlist = []
        for i, ((ocls,), (oreg,)) in enumerate ( zip ( olist[::2], olist[1::2] ) ):
            stride = 2**(i + 2)    # 4,8,16,32,64,128
            s_d2 = stride / 2
            s_m4 = stride * 4

            for hindex, windex in zip(*np.where(ocls[...,1] > 0.05)):
                score = ocls[hindex, windex, 1]
                loc   = oreg[hindex, windex, :]
                priors = np.array([windex * stride + s_d2, hindex * stride + s_d2, s_m4, s_m4])
                priors_2p = priors[2:]
                box = np.concatenate((priors[:2] + loc[:2] * 0.1 * priors_2p,
                                      priors_2p * np.exp(loc[2:] * 0.2)) )
                box[:2] -= box[2:] / 2
                box[2:] += box[:2]

                bboxlist.append([*box, score])

        bboxlist = np.array(bboxlist)
        if len(bboxlist) == 0:
            bboxlist = np.zeros((1, 5))

        bboxlist = bboxlist[nms(bboxlist, 0.3), :]
        bboxlist = [ x[:-1] for x in bboxlist if x[-1] >= 0.5]
        return bboxlist

    #img = np.random.uniform ( size=(480,270,3) ) * 255
    img = cv2.imread ( r"D:\DevelopPython\test\00000.png" )

    torch_img = torch.from_numpy( np.expand_dims((img - np.array([104, 117, 123])).transpose(2, 0, 1),0) ).float()

    t = time.time()
    with torch.no_grad():
        olist_torch = [x.data.cpu().numpy() for x in fd_torch( torch.autograd.Variable( torch_img) )]
    print ("torch took:", time.time() - t)

    fd_keras_path = r"D:\DevelopPython\test\S3FD.npy"
    #if Path(fd_keras_path).exists():
    #    fd_keras = keras.models.load_model (fd_keras_path)
    #else:

    #fd_keras = sf3d_keras(img.shape, fd_torch)
    #fd_keras.save_weights (fd_keras_path)

    fd_keras = S3FD()
    fd_keras.build()

    #transfer weights
    def convd2d_from_torch(torch_layer):
        result = [ torch_layer.weight.data.numpy().transpose(2,3,1,0) ]
        if torch_layer.bias is not None:
            result +=  [ torch_layer.bias.data.numpy().reshape( (1,1,1,-1) ) ]
        return result

    def l2norm_from_torch(torch_layer):
        result = [ torch_layer.weight.data.numpy().reshape( (1,1,1,-1) ) ]
        return result

    fd_keras.conv1_1.set_weights ( convd2d_from_torch(fd_torch.conv1_1) )
    fd_keras.conv1_2.set_weights ( convd2d_from_torch(fd_torch.conv1_2) )

    fd_keras.conv2_1.set_weights ( convd2d_from_torch(fd_torch.conv2_1) )
    fd_keras.conv2_2.set_weights ( convd2d_from_torch(fd_torch.conv2_2) )

    fd_keras.conv3_1.set_weights ( convd2d_from_torch(fd_torch.conv3_1) )
    fd_keras.conv3_2.set_weights ( convd2d_from_torch(fd_torch.conv3_2) )
    fd_keras.conv3_3.set_weights ( convd2d_from_torch(fd_torch.conv3_3) )

    fd_keras.conv4_1.set_weights ( convd2d_from_torch(fd_torch.conv4_1) )
    fd_keras.conv4_2.set_weights ( convd2d_from_torch(fd_torch.conv4_2) )
    fd_keras.conv4_3.set_weights ( convd2d_from_torch(fd_torch.conv4_3) )

    fd_keras.conv5_1.set_weights ( convd2d_from_torch(fd_torch.conv5_1) )
    fd_keras.conv5_2.set_weights ( convd2d_from_torch(fd_torch.conv5_2) )
    fd_keras.conv5_3.set_weights ( convd2d_from_torch(fd_torch.conv5_3) )

    fd_keras.fc6.set_weights ( convd2d_from_torch(fd_torch.fc6) )
    fd_keras.fc7.set_weights ( convd2d_from_torch(fd_torch.fc7) )

    fd_keras.conv6_1.set_weights ( convd2d_from_torch(fd_torch.conv6_1) )
    fd_keras.conv6_2.set_weights ( convd2d_from_torch(fd_torch.conv6_2) )

    fd_keras.conv7_1.set_weights ( convd2d_from_torch(fd_torch.conv7_1) )
    fd_keras.conv7_2.set_weights ( convd2d_from_torch(fd_torch.conv7_2) )

    fd_keras.conv3_3_norm.set_weights ( l2norm_from_torch(fd_torch.conv3_3_norm))
    fd_keras.conv4_3_norm.set_weights ( l2norm_from_torch(fd_torch.conv4_3_norm))
    fd_keras.conv5_3_norm.set_weights ( l2norm_from_torch(fd_torch.conv5_3_norm))

    fd_keras.conv3_3_norm_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.conv3_3_norm_mbox_conf) )
    fd_keras.conv3_3_norm_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.conv3_3_norm_mbox_loc) )

    fd_keras.conv4_3_norm_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.conv4_3_norm_mbox_conf) )
    fd_keras.conv4_3_norm_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.conv4_3_norm_mbox_loc) )

    fd_keras.conv5_3_norm_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.conv5_3_norm_mbox_conf) )
    fd_keras.conv5_3_norm_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.conv5_3_norm_mbox_loc) )

    fd_keras.fc7_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.fc7_mbox_conf) )
    fd_keras.fc7_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.fc7_mbox_loc) )

    fd_keras.conv6_2_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.conv6_2_mbox_conf) )
    fd_keras.conv6_2_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.conv6_2_mbox_loc) )

    fd_keras.conv7_2_mbox_conf.set_weights ( convd2d_from_torch(fd_torch.conv7_2_mbox_conf) )
    fd_keras.conv7_2_mbox_loc .set_weights ( convd2d_from_torch(fd_torch.conv7_2_mbox_loc) )

    fd_keras.save_weights ( fd_keras_path )

    import code
    code.interact(local=dict(globals(), **locals()))



    inp = tf.placeholder(tf.float32, (None,None,None,3) )
    outp = fd_keras(inp)

    t = time.time()
    olist_keras = nn.tf_sess.run (outp, feed_dict={inp: np.expand_dims(img,0)})
    print ("keras took:", time.time() - t)

    abs_diff = 0
    for i in range(len(olist_torch)):
        td = np.transpose( olist_torch[i], (0,2,3,1) )
        kd = olist_keras[i]
        td = td[...,-1]
        kd = kd[...,-1]
        p = np.ndarray.flatten(td-kd)
        diff = np.sum ( np.abs(p))
        print ("nparams=", len(p), " diff=",diff, "diff_per_param=", diff / len(p)  )
        abs_diff += diff
    print ("Total absolute diff = ", abs_diff)

    import code
    code.interact(local=dict(globals(), **locals()))

    t = time.time()
    bbox_torch = detect_torch(olist_torch)
    bbox_torch = bbox_torch[ nms(bbox_torch, 0.3) , :]
    bbox_torch = [x for x in bbox_torch if x[-1] >= 0.5]
    print ("torch took:", time.time() - t)

    t = time.time()
    bbox_keras = detect_keras(olist_keras)
    print ("keras took:", time.time() - t)

    #bbox_keras = bbox_keras[ nms(bbox_keras, 0.3) , :]
    #bbox_keras = [x for x in bbox_keras if x[-1] >= 0.5]

    print (bbox_torch)
    print (bbox_keras)

    import code
    code.interact(local=dict(globals(), **locals()))
    #===============================================================================











    print("importing")
    """
    from core.leras import nn
    nn.import_tf( device_config=nn.device.Config(force_gpu_idx=1) )
    tf = nn.tf
    filepath =  r'D:\DevelopPython\test\00000.png'

    img = cv2.imread(filepath).astype(np.float32) / 255.0
    h,w,c = img.shape

    inp  = tf.placeholder(tf.float32, (1, h,w,c) )
    x = nn.gaussian_blur()(inp)

    q = nn.style_loss()(x, inp)
    import code
    code.interact(local=dict(globals(), **locals()))

    a = nn.tf_sess.run (x, feed_dict={inp:img[None,...]} )

    cv2.imshow("", (a[0]*255).astype(np.uint8))
    cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))
    """

    from core.leras import nn
    nn.import_tf( device_config=nn.device.Config(force_gpu_idx=1) )

    tf = nn.tf
    tf_sess = nn.tf_sess

    import code
    code.interact(local=dict(globals(), **locals()))

    class SubEncoder(nn.ModelBase):
        def on_build(self):
            self.conv1  = nn.Conv2D( 3, 3, kernel_size=3, padding='SAME', wscale_gain=np.sqrt(2) )

        def call(self, x):
            x = self.conv1(x)
            return x

    class Encoder(nn.ModelBase):
        def on_build(self):
            self.conv1 = SubEncoder()
            self.dense1 = nn.Dense( 64*64*3, 1 )

        def call(self, x):
            x = self.conv1(x)
            x = nn.flatten()(x)
            x = self.dense1(x)
            return x

    with tf.device('/CPU:0'):

        inp  = tf.placeholder(tf.float32, (None, 64,64,3) )
        real = tf.placeholder(tf.float32, (None, 1) )

        encoder = Encoder(name='encoder')
        encoder.init_weights()
        #encoder.save_weights(r"D:\enc.h5")
        #encoder.load_weights(r"D:\enc.h5")

        with tf.device('/GPU:0'):
            x = encoder(inp)

            loss = tf.reduce_sum(tf.square(x - real))

        enc_opt = nn.RMSprop(name='enc_opt')

        with tf.device('/GPU:0'):
            grads_vars = nn.gradients(loss, encoder.get_weights() )

            apply_op = enc_opt.get_updates (grads_vars )

        enc_opt.init_weights()

    inp1 = np.random.uniform (size=(1,64,64,3))
    real1 = np.random.uniform (size=(1,1))

    l, _ = nn.tf_sess.run ( [loss, apply_op], feed_dict={inp:inp1, real:real1})

    #print ( tf_get_value(W) )

    import code
    code.interact(local=dict(globals(), **locals()))


    src_real = np.random.uniform ( size=(1,64,64,3) ).astype(np.float32)
    dst_real = np.random.uniform ( size=(1,64,64,3) ).astype(np.float32)

    with tf.device('/CPU:0'):
        src_inp = KL.Input( (64,64,3) )
        dst_inp = KL.Input( (64,64,3) )

        x = src_inp
        x = KL.Conv2D(3, kernel_size=3, padding='same')(x)
        enc = KM.Model(src_inp, x)

        code_inp = KL.Input( enc.outputs[0].shape[1:] )
        x = code_inp
        x = KL.Conv2D(3, kernel_size=3, padding='same')(x)
        dec_src = KM.Model(code_inp, x)

        code_inp = KL.Input( enc.outputs[0].shape[1:] )
        x = code_inp
        x = KL.Conv2D(3, kernel_size=3, padding='same')(x)
        dec_dst = KM.Model(code_inp, x)

        """
        with tf.device('/GPU:0'):
            with tf.GradientTape() as src_tape:
                t = time.time()

                code = enc(src_inp)
                pred_src = dec_src(code)

                print(f"src took: {time.time()-t}")
                src_loss = tf.math.reduce_mean ( tf.math.abs(pred_src-src_real) )
        """
        with tf.device('/GPU:0'):
            with tf.GradientTape() as dst_tape:
                t = time.time()

                code = enc(dst_inp)
                pred_dst = dec_dst(code)

                print(f"dst took: {time.time()-t}")
                dst_loss = tf.math.reduce_mean ( tf.math.abs(pred_dst-dst_real) )


        #grad1 = src_tape.gradient(src_loss, enc.trainable_variables)
        grad2 = dst_tape.gradient(dst_loss, enc.trainable_variables)

        """
        grad = []
        for g1,g2 in zip(grad1,grad2):
            g = tf.concat( [tf.expand_dims(g1,0), tf.expand_dims(g2,0)], axis=0)
            g = tf.reduce_mean(g, 0)
            grad.append(g)
        """

        apply_op = optimizer.apply_gradients(zip(grad2, enc.trainable_variables))

        tf_sess.run ( tf.global_variables_initializer() )

        dl, _ = nn.tf_sess.run ( [dst_loss, apply_op], feed_dict={dst_inp: src_real})
        print(dl)





    import code
    code.interact(local=dict(globals(), **locals()))



    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=1) ), locals(), globals() )#

    from facelib import FaceEnhancer

    filepath =  r'D:\DevelopPython\test\00000.jpg'
    img = cv2.imread(filepath).astype(np.float32) / 255.0

    fe = FaceEnhancer()
    final_img = fe.enhance( img )

    cv2.imshow("", (final_img*255).astype(np.uint8) )
    cv2.waitKey(0)








    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=1, use_fp16=False) ), locals(), globals() )#

    filepath =  r'D:\DevelopPython\test\ct_00003.jpg'
    img = cv2.imread(filepath).astype(np.float32) / 255.0

    inp = Input( (None,None,3) )
    x = AveragePooling2D(pool_size=2, strides=2, padding='same')(inp)
    model = keras.models.Model (inp, x)
    x, = K.function([inp],[x]) ( [img[None,...] ])

    cv2.imshow("", (x[0]*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=1, use_fp16=False) ), locals(), globals() )#
    tf = nn.tf





    def load_pb(path_to_pb):
        with tf.gfile.GFile(path_to_pb, "rb") as f:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(f.read())
        with tf.Graph().as_default() as graph:
            tf.import_graph_def(graph_def, name='')
            return graph

    graph = load_pb (r"D:\DevelopPython\test\gigavideo.pb")


    input0 = graph.get_tensor_by_name('VideoSR_Unet/inputFrame0:0')
    input1 = graph.get_tensor_by_name('VideoSR_Unet/inputFrame1:0')
    input2 = graph.get_tensor_by_name('VideoSR_Unet/inputFrame2:0')
    input3 = graph.get_tensor_by_name('VideoSR_Unet/inputFrame3:0')
    input4 = graph.get_tensor_by_name('VideoSR_Unet/inputFrame4:0')
    output = graph.get_tensor_by_name('VideoSR_Unet/Out4X/output/add:0')

    #filepath =  r'D:\DevelopPython\test\00000.jpg'
    #img = cv2.imread(filepath).astype(np.float32) / 255.0
    #inp_img = img *2 - 1
    #inp_img = cv2.resize (inp_img, (192,192) )



    sess = tf.Session(graph=graph, config=nn.tf_sess_config)

    writer = tf.summary.FileWriter(r'D:\logs', nn.tf_sess.graph)

    def get_op_value(op_name, n_output=0):
        return sess.run ([ graph.get_operation_by_name(op_name).outputs[n_output] ])[0].astype(K.floatx())

    #

    import code
    code.interact(local=dict(globals(), **locals()))






    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config() ), locals(), globals() )


    batch_size = 1024

    i_t = Input ( (256,256,3) )
    j_t = Input ( (256,256,3) )

    outputs = []
    #for i in range(batch_size):
    outputs += [ K.sum( K.abs(i_t-j_t), axis=[1,2,3] ) ]

    func = K.function ( [i_t,j_t], outputs)


    k1 = np.random.random ( size=(batch_size,256,256,3) )
    k2 = np.random.random ( size=(1,256,256,3) )

    t = time.time()
    result = func ([k1,k2])
    print (f"time took: {time.time()-t}")
    t = time.time()
    result = func ([k1,k2])
    print (f"time took: {time.time()-t}")
    import code
    code.interact(local=dict(globals(), **locals()))




    a = []

    for filename in io.progress_bar_generator(image_paths, ""):
        a.append ( cv2_imread(filename) )



    import code
    code.interact(local=dict(globals(), **locals()))

    cap = cv2.VideoCapture(r'D:\DevelopPython\test\test1.mp4')

    import code
    code.interact(local=dict(globals(), **locals()))

    libdll = CDLL(r"D:\DevelopPython\Projects\TestCPPDLL\x64\Release\TestCPPDLL.dll")
    libdll.ST2DFloat.argtypes = ( \
        c_int,
        c_void_p,
        c_void_p,
        c_void_p,
        c_void_p,
        c_void_p
        )

    dflimg = DFLJPG.load ( r'D:\DevelopPython\test\dflimg_1.jpg')
    real_lmrks = dflimg.get_landmarks()
    lmrks = dflimg.get_source_landmarks()[17:].astype(np.float32)

    pts1_bytes = lmrks.reshape ( np.prod(lmrks.shape) ).tobytes()
    pts2_bytes = landmarks_2D.reshape ( np.prod(landmarks_2D.shape) ).tobytes()
    rot_buf = create_string_buffer( 4*4 )
    trans_buf = create_string_buffer( 4*2 )
    scale_buf = create_string_buffer( 4*1 )

    libdll.ST2DFloat ( len(lmrks), pts1_bytes, pts2_bytes, rot_buf, trans_buf, scale_buf )
    rot = np.frombuffer(rot_buf, dtype=np.float32)
    trans = np.frombuffer(trans_buf, dtype=np.float32)
    scale = np.frombuffer(scale_buf, dtype=np.float32)


    mat = np.concatenate ([ rot.reshape ( (2,2) ),
                            trans.reshape ( (2,1) )*(1/scale) ], axis=-1 )
    new_lmrks = LandmarksProcessor.transform_points(lmrks, mat)

    #import code
    #code.interact(local=dict(globals(), **locals()))
    new_lmrks *= 3
    new_lmrks += [127,127]


    img = np.zeros ( (256,256,3), dtype=np.uint8 )

    for pt in new_lmrks:
        x,y = pt
        cv2.circle(img, (x, y), 1, (255,0,0) )

    for pt in real_lmrks:
        x,y = pt.astype(np.int)
        cv2.circle(img, (x, y), 1, (0,0,255) )

    cv2.imshow ("", img)
    cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))

    img_src = cv2.imread(r'D:\DevelopPython\test\ct_trg1.jpg')/255.0

    img_trg = cv2.imread(r'D:\DevelopPython\test\ct_src1.jpg')/255.0


    screen1 = (color_transfer_mix(img_src, img_trg)*255.0).astype(np.uint8)
    screen2 = (color_transfer_mix2(img_src, img_trg)*255.0).astype(np.uint8)
    screen = np.concatenate([screen1,screen2], axis=1)
    cv2.imshow ("", screen )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))



    img_src = cv2.imread(r'D:\DevelopPython\test\ct_trg1.jpg')
    img_src_float = img_src.astype(np.float32)
    img_src_shape = img_src.shape

    img_src_lab = cv2.cvtColor(img_src, cv2.COLOR_BGR2LAB)
    img_src_l = img_src_lab.copy()
    img_src_l[...,0] = (np.ones_like (img_src_l[...,0])*100).astype(np.uint8)
    img_src_l = cv2.cvtColor(img_src_l, cv2.COLOR_LAB2BGR)

    img_trg = cv2.imread(r'D:\DevelopPython\test\ct_src1.jpg')
    img_trg_float = img_trg.astype(np.float32)
    img_trg_shape = img_trg.shape


    img_trg_lab = cv2.cvtColor(img_trg, cv2.COLOR_BGR2LAB)
    img_trg_l = img_trg_lab.copy()
    img_trg_l[...,0] = (np.ones_like (img_trg_l[...,0])*100).astype(np.uint8)
    img_trg_l = cv2.cvtColor(img_trg_l, cv2.COLOR_LAB2BGR)


    t = time.time()


    #img_rct_light = imagelib.color_transfer_sot( img_src_lab[...,0:1].astype(np.float32), img_trg_lab[...,0:1].astype(np.float32) )

    img_src_light = img_src_lab[...,0:1]
    img_trg_light = img_trg_lab[...,0:1]


#
#
    #img_rct_light = img_src_light * 1.0#( img_trg_light.mean()/img_src_light.mean() )
    #img_rct_light = np.clip (img_rct_light, 0, 100).astype(np.uint8)

    img_rct_light = imagelib.linear_color_transfer( img_src_lab[...,0:1].astype(np.float32)/255.0,
                                                    img_trg_lab[...,0:1].astype(np.float32)/255.0 )[...,0:1] *255.0


    img_rct_light = np.clip (img_rct_light, 0, 255).astype(np.uint8)




    img_rct = imagelib.color_transfer_sot( img_src_l.astype(np.float32), img_trg_l.astype(np.float32) )
    img_rct = np.clip(img_rct, 0, 255)
    img_rct_l = img_rct.astype(np.uint8)

    img_rct = cv2.cvtColor(img_rct_l, cv2.COLOR_BGR2LAB)
    img_rct[...,0] = img_rct_light[...,0]#img_src_lab[...,0]
    img_rct = cv2.cvtColor(img_rct, cv2.COLOR_LAB2BGR)

    #import code
    #code.interact(local=dict(globals(), **locals()))

    screen1 = np.concatenate ([img_src, img_src_l, img_trg, img_trg_l, img_rct_l,
                              ], axis=1)
    screen2 = np.concatenate ([
                              np.repeat(img_src_lab[...,0:1], 3, -1),
                              np.repeat(img_trg_lab[...,0:1], 3, -1),
                              np.repeat(img_rct_light, 3, -1),

                              img_rct,img_rct], axis=1)
    screen = np.concatenate([screen1, screen2], axis=0 )
    cv2.imshow ("", screen )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    img_src = cv2.imread(r'D:\DevelopPython\test\ct_src.jpg')
    img_src_shape = img_src.shape

    img = cv2.cvtColor(img_src, cv2.COLOR_BGR2LAB)
    img[...,0] = (np.ones_like (img[...,0])*100).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_LAB2BGR)


    #screen = np.concatenate ([img_src, img_trg, img_rct], axis=1)
    cv2.imshow ("", img )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    image_paths = pathex.get_image_paths(r"E:\FakeFaceVideoSources\Datasets\CelebA\aligned_def\aligned")

    out_path = Path("E:\FakeFaceVideoSources\Datasets\CelebA\aligned_def\aligned_out")


    while True:

        filename1 = image_paths[ np.random.randint(len(image_paths)) ]
        filename2 = image_paths[ np.random.randint(len(image_paths)) ]


        img1 = cv2_imread(filename1).astype(np.float32)
        img1_mask = LandmarksProcessor.get_image_hull_mask (img1.shape , DFLJPG.load (filename1).get_landmarks() )

        img2 = cv2_imread(filename2).astype(np.float32)
        img2_mask = LandmarksProcessor.get_image_hull_mask (img2.shape , DFLJPG.load (filename2).get_landmarks() )

        mask = img1_mask*img2_mask

        img1_masked = np.clip(img1*mask, 0,255)
        img2_masked = np.clip(img2*mask, 0,255)



        img1_sot = imagelib.color_transfer_sot (img1_masked, img2_masked)
        img1_sot = np.clip(img1_sot, 0, 255)

        l,t,w,h = cv2.boundingRect( (mask*255).astype(np.uint8) )

        img_ct = cv2.seamlessClone( img1_sot.astype(np.uint8), img2.astype(np.uint8), (mask*255).astype(np.uint8), (int(l+w/2),int(t+h/2)) , cv2.NORMAL_CLONE )

        #img_ct = out_img.astype(dtype=np.float32) / 255.0

        #img_ct = imagelib.color_transfer_sot (img1_masked, img2_masked)
        #img_ct = imagelib.linear_color_transfer ( img1_masked/255.0, img2_masked/255.0) * 255.0
        #img_ct = np.clip(img_ct, 0, 255)

        #img1_mask_blur = cv2.blur(img1_mask, (21,21) )[...,None]

        #img_ct = img1*(1-img1_mask)+img_ct*img1_mask

        screen = np.concatenate ([img1, img2, img1_sot, img_ct], axis=1)


        cv2.imshow("", screen.astype(np.uint8) )
        cv2.waitKey(0)


    import code
    code.interact(local=dict(globals(), **locals()))

    img_src = cv2.imread(r'D:\DevelopPython\test\ct_src2.jpg')
    img_src_float = img_src.astype(np.float32)
    img_src_shape = img_src.shape

    img_trg = cv2.imread(r'D:\DevelopPython\test\ct_trg2.jpg')
    img_trg_float = img_trg.astype(np.float32)
    img_trg_shape = img_trg.shape


    t = time.time()

    img_rct = imagelib.linear_color_transfer( (img_src/255.0).astype(np.float32), (img_trg/255.0).astype(np.float32) ) * 255.0
    img_rct = np.clip(img_rct, 0, 255)
    img_rct = img_rct.astype(np.uint8)

    screen = np.concatenate ([img_src, img_trg, img_rct], axis=1)
    cv2.imshow ("", screen )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    #===============================================================================

    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(cpu_only=True) ), locals(), globals() )

    import torch
    import torch.nn as nn
    import torch.nn.functional as F


    import face_alignment
    fa = face_alignment.FaceAlignment(face_alignment.LandmarksType._2D,enable_cuda=False,enable_cudnn=False,use_cnn_face_detector=False).face_alignemnt_net
    fa.eval()


    def ConvBlock(out_planes, input, srctorch):
        in_planes = K.int_shape(input)[-1]
        x = input
        x = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d(srctorch.bn1) )(x)
        x = ReLU() (x)
        x = out1 = Conv2D( int(out_planes/2), kernel_size=3, strides=1, padding='valid', use_bias = False, weights=t2kw_conv2d(srctorch.conv1) ) (ZeroPadding2D(1)(x))

        x = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d(srctorch.bn2) )(x)
        x = ReLU() (x)
        x = out2 = Conv2D( int(out_planes/4), kernel_size=3, strides=1, padding='valid', use_bias = False, weights=t2kw_conv2d(srctorch.conv2) ) (ZeroPadding2D(1)(x))

        x = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d(srctorch.bn3) )(x)
        x = ReLU() (x)
        x = out3 = Conv2D( int(out_planes/4), kernel_size=3, strides=1, padding='valid', use_bias = False, weights=t2kw_conv2d(srctorch.conv3) ) (ZeroPadding2D(1)(x))

        x = Concatenate()([out1, out2, out3])

        if in_planes != out_planes:
            downsample = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d(srctorch.downsample[0]) )(input)
            downsample = ReLU() (downsample)
            downsample = Conv2D( out_planes, kernel_size=1, strides=1, padding='valid', use_bias = False, weights=t2kw_conv2d(srctorch.downsample[2]) ) (downsample)
            x = Add ()([x, downsample])
        else:
            x = Add ()([x, input])


        return x

    def HourGlass (depth, input, srctorch):
        up1 = ConvBlock(256, input, srctorch._modules['b1_%d' % (depth)])

        low1 = AveragePooling2D (pool_size=2, strides=2, padding='valid' )(input)
        low1 = ConvBlock (256, low1, srctorch._modules['b2_%d' % (depth)])

        if depth > 1:
            low2 = HourGlass (depth-1, low1, srctorch)
        else:
            low2 = ConvBlock(256, low1, srctorch._modules['b2_plus_%d' % (depth)])

        low3 = ConvBlock(256, low2, srctorch._modules['b3_%d' % (depth)])

        up2 = UpSampling2D(size=2) (low3)
        return Add() ( [up1, up2] )

    FAN_Input = Input ( (256, 256, 3) )

    x = FAN_Input

    x = Conv2D (64, kernel_size=7, strides=2, padding='valid', weights=t2kw_conv2d(fa.conv1))(ZeroPadding2D(3)(x))
    x = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d(fa.bn1))(x)
    x = ReLU()(x)

    x = ConvBlock (128, x, fa.conv2)
    x = AveragePooling2D (pool_size=2, strides=2, padding='valid') (x)
    x = ConvBlock (128, x, fa.conv3)
    x = ConvBlock (256, x, fa.conv4)

    outputs = []
    previous = x
    for i in range(4):
        ll = HourGlass (4, previous, fa._modules['m%d' % (i) ])
        ll = ConvBlock (256, ll, fa._modules['top_m_%d' % (i)])

        ll = Conv2D(256, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d( fa._modules['conv_last%d' % (i)] ) ) (ll)
        ll = BatchNormalization(momentum=0.1, epsilon=1e-05, weights=t2kw_bn2d( fa._modules['bn_end%d' % (i)] ) )(ll)
        ll = ReLU() (ll)

        tmp_out = Conv2D(68, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d( fa._modules['l%d' % (i)] ) ) (ll)
        outputs.append(tmp_out)

        if i < 4 - 1:
            ll = Conv2D(256, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d( fa._modules['bl%d' % (i)] ) ) (ll)
            previous = Add() ( [previous, ll, KL.Conv2D(256, kernel_size=1, strides=1, padding='valid', weights=t2kw_conv2d( fa._modules['al%d' % (i)] ) ) (tmp_out) ] )



    rnd_data = np.random.randint (256, size=(1,256,256,3) ).astype(np.float32)

    with torch.no_grad():
        fa_out_tensor = fa( torch.autograd.Variable( torch.from_numpy(rnd_data.transpose(0,3,1,2) ) ) )[-1].data.cpu()
    fa_out = fa_out_tensor.numpy()

    FAN_model = Model(FAN_Input, outputs[-1] )
    FAN_model.save_weights (r"D:\DevelopPython\test\2DFAN-4.h5")
    FAN_model_func = K.function (FAN_model.inputs, FAN_model.outputs)

    m_out, = FAN_model_func([ rnd_data ])

    m_out = m_out.transpose(0,3,1,2)

    diff = np.sum(np.abs(np.ndarray.flatten(fa_out)-np.ndarray.flatten(m_out)))
    print (f"====== diff {diff} =======")

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(cpu_only=True) ), locals(), globals() )

    import torch
    import torch.nn as nn
    import torch.nn.functional as F




    def conv_bn(inp, oup, kernel, stride, padding=1):
        return nn.Sequential(
            nn.Conv2d(inp, oup, kernel, stride, padding, bias=False),
            nn.BatchNorm2d(oup),
            nn.ReLU(inplace=True))

    class InvertedResidual(nn.Module):
        def __init__(self, inp, oup, stride, use_res_connect, expand_ratio=6):
            super(InvertedResidual, self).__init__()
            self.stride = stride
            assert stride in [1, 2]

            self.use_res_connect = use_res_connect

            self.conv = nn.Sequential(
                nn.Conv2d(inp, inp * expand_ratio, 1, 1, 0, bias=False),
                nn.BatchNorm2d(inp * expand_ratio),
                nn.ReLU(inplace=True),
                nn.Conv2d(
                    inp * expand_ratio,
                    inp * expand_ratio,
                    3,
                    stride,
                    1,
                    groups=inp * expand_ratio,
                    bias=False),
                nn.BatchNorm2d(inp * expand_ratio),
                nn.ReLU(inplace=True),
                nn.Conv2d(inp * expand_ratio, oup, 1, 1, 0, bias=False),
                nn.BatchNorm2d(oup),
            )

        def forward(self, x):
            if self.use_res_connect:
                return x + self.conv(x)
            else:
                return self.conv(x)


    class PFLDInference(nn.Module):
        def __init__(self):
            super(PFLDInference, self).__init__()

            self.conv1 = nn.Conv2d(
                3, 64, kernel_size=3, stride=2, padding=1, bias=False)
            self.bn1 = nn.BatchNorm2d(64)
            self.relu = nn.ReLU(inplace=True)

            self.conv2 = nn.Conv2d(
                64, 64, kernel_size=3, stride=1, padding=1, bias=False)
            self.bn2 = nn.BatchNorm2d(64)
            self.relu = nn.ReLU(inplace=True)

            self.conv3_1 = InvertedResidual(64, 64, 2, False, 2)

            self.block3_2 = InvertedResidual(64, 64, 1, True, 2)
            self.block3_3 = InvertedResidual(64, 64, 1, True, 2)
            self.block3_4 = InvertedResidual(64, 64, 1, True, 2)
            self.block3_5 = InvertedResidual(64, 64, 1, True, 2)

            self.conv4_1 = InvertedResidual(64, 128, 2, False, 2)

            self.conv5_1 = InvertedResidual(128, 128, 1, False, 4)
            self.block5_2 = InvertedResidual(128, 128, 1, True, 4)
            self.block5_3 = InvertedResidual(128, 128, 1, True, 4)
            self.block5_4 = InvertedResidual(128, 128, 1, True, 4)
            self.block5_5 = InvertedResidual(128, 128, 1, True, 4)
            self.block5_6 = InvertedResidual(128, 128, 1, True, 4)

            self.conv6_1 = InvertedResidual(128, 16, 1, False, 2)  # [16, 14, 14]

            self.conv7 = conv_bn(16, 32, 3, 2)  # [32, 7, 7]
            self.conv8 = nn.Conv2d(32, 128, 7, 1, 0)  # [128, 1, 1]
            self.bn8 = nn.BatchNorm2d(128)

            self.avg_pool1 = nn.AvgPool2d(14)
            self.avg_pool2 = nn.AvgPool2d(7)
            self.fc = nn.Linear(176, 196)

        def forward(self, x):  # x: 3, 112, 112
            x = self.relu(self.bn1(self.conv1(x)))  # [64, 56, 56]
            x = self.relu(self.bn2(self.conv2(x)))  # [64, 56, 56]
            x = self.conv3_1(x)
            x = self.block3_2(x)
            x = self.block3_3(x)
            x = self.block3_4(x)
            out1 = self.block3_5(x)

            x = self.conv4_1(out1)
            x = self.conv5_1(x)
            x = self.block5_2(x)
            x = self.block5_3(x)
            x = self.block5_4(x)
            x = self.block5_5(x)
            x = self.block5_6(x)
            x = self.conv6_1(x)

            x1 = self.avg_pool1(x)
            x1 = x1.view(x1.size(0), -1)

            x = self.conv7(x)
            x2 = self.avg_pool2(x)
            x2 = x2.view(x2.size(0), -1)

            x3 = self.relu(self.conv8(x))
            x3 = x3.view(x1.size(0), -1)

            multi_scale = torch.cat([x1, x2, x3], 1)
            landmarks = self.fc(multi_scale)

            return out1, landmarks

    mw = torch.load(r"D:\DevelopPython\test\PFLD.pth.tar", map_location=torch.device('cpu'))
    mw = mw['plfd_backbone']


    """

    class TorchBatchNorm2D(keras.engine.Layer):
        def __init__(self, axis=-1, momentum=0.1, epsilon=1e-5, **kwargs):
            super(TorchBatchNorm2D, self).__init__(**kwargs)
            self.supports_masking = True
            self.axis = axis
            self.momentum = momentum
            self.epsilon = epsilon

        def build(self, input_shape):
            dim = input_shape[self.axis]
            if dim is None:
                raise ValueError('Axis ' + str(self.axis) + ' of '
                                'input tensor should have a defined dimension '
                                'but the layer received an input with shape ' +
                                str(input_shape) + '.')
            shape = (dim,)
            self.gamma = self.add_weight(shape=shape, name='gamma', initializer='ones', regularizer=None, constraint=None)
            self.beta = self.add_weight(shape=shape, name='beta', initializer='zeros', regularizer=None, constraint=None)
            self.moving_mean = self.add_weight(shape=shape, name='moving_mean', initializer='zeros', trainable=False)
            self.moving_variance = self.add_weight(shape=shape, name='moving_variance', initializer='ones', trainable=False)
            self.built = True

        def call(self, inputs, training=None):
            input_shape = K.int_shape(inputs)

            broadcast_shape = [1] * len(input_shape)
            broadcast_shape[self.axis] = input_shape[self.axis]

            reduction_axes = list(range(len(input_shape)))
            del reduction_axes[self.axis]

            broadcast_mean = K.mean(inputs, reduction_axes, keepdims=True)
            broadcast_variance = K.var(inputs, reduction_axes, keepdims=True)
            broadcast_gamma = K.reshape(self.gamma, broadcast_shape)
            broadcast_beta = K.reshape(self.beta, broadcast_shape)

            return (inputs - broadcast_mean) / ( K.sqrt(broadcast_variance + K.constant(self.epsilon, dtype=K.floatx() )) ) * broadcast_gamma + broadcast_beta

        def get_config(self):
            config = { 'axis': self.axis, 'momentum': self.momentum, 'epsilon': self.epsilon }
            base_config = super(TorchBatchNorm2D, self).get_config()
            return dict(list(base_config.items()) + list(config.items()))


    def InvertedResidual(out_dim, strides, use_res_connect, expand_ratio=6, name_prefix=""):

        def func(inp):
            c = K.int_shape(inp)[-1]
            x = inp
            x = Conv2D (c*expand_ratio, kernel_size=1, strides=1, padding='valid', use_bias=False, name=name_prefix+'_conv0')(x)
            x = TorchBatchNorm2D(name=name_prefix+'_conv1')(x)
            x = ReLU()(x)

            x = DepthwiseConv2D ( kernel_size=3, strides=strides, padding='valid', use_bias=False, name=name_prefix+'_conv3')(ZeroPadding2D(1)(x))
            x = TorchBatchNorm2D(name=name_prefix+'_conv4')(x)
            x = ReLU()(x)

            x = Conv2D (out_dim, kernel_size=1, strides=1, padding='valid', use_bias=False, name=name_prefix+'_conv6')(x)
            x = TorchBatchNorm2D(name=name_prefix+'_conv7')(x)


            if use_res_connect:
                x = Add()([inp, x])

            return x

        return func

    PFLD_Input = Input ( (112, 112, 3) )

    x = PFLD_Input

    x = Conv2D (64, kernel_size=3, strides=2, padding='valid', use_bias=False, name='conv1')(ZeroPadding2D(1)(x))
    x = TorchBatchNorm2D(name='bn1')(x)
    x = ReLU()(x)


    x = Conv2D (64, kernel_size=3, strides=1, padding='valid', use_bias=False, name='conv2')(ZeroPadding2D(1)(x))
    x = TorchBatchNorm2D(name='bn2')(x)
    x = ReLU()(x)



    x = InvertedResidual(64, 2, False, 2, 'conv3_1')(x)
    x = InvertedResidual(64, 1, True, 2, 'block3_2')(x)
    x = InvertedResidual(64, 1, True, 2, 'block3_3')(x)
    x = InvertedResidual(64, 1, True, 2, 'block3_4')(x)
    x = InvertedResidual(64, 1, True, 2, 'block3_5')(x)
    x = InvertedResidual(128, 2, False, 2, 'conv4_1')(x)
    x = InvertedResidual(128, 1, False, 4, 'conv5_1')(x)

    x = InvertedResidual(128, 1, True, 4, 'block5_2')(x)
    x = InvertedResidual(128, 1, True, 4, 'block5_3')(x)
    x = InvertedResidual(128, 1, True, 4, 'block5_4')(x)
    x = InvertedResidual(128, 1, True, 4, 'block5_5')(x)
    x = InvertedResidual(128, 1, True, 4, 'block5_6')(x)

    x = InvertedResidual(16, 1, False, 2, 'conv6_1')(x)

    x1 = AveragePooling2D(14)(x)
    x1 = x1 = Flatten()(x1)

    x = Conv2D (32, kernel_size=3, strides=2, padding='valid', use_bias=False, name='conv7_0')(ZeroPadding2D(1)(x))
    x = TorchBatchNorm2D(name='conv7_1')(x)
    x = ReLU()(x)

    x2 = AveragePooling2D(7)(x)
    x2 = x2 = Flatten()(x2)

    x3 = Conv2D (128, kernel_size=7, strides=1, padding='valid', name='conv8')(x)

    x3 = ReLU()(x3)
    x3 = Flatten()(x3)

    x = Concatenate(axis=-1)([x1,x2,x3])
    x = Dense(196, name='fc')(x)

    PFLD_model = Model(PFLD_Input, x )

    try:
        PFLD_model.get_layer('conv1').set_weights ( tdict2kw_conv2d (mw['conv1.weight']) )
        PFLD_model.get_layer('bn1').set_weights ( tdict2kw_bn2d (mw, 'bn1') )
        PFLD_model.get_layer('conv2').set_weights ( tdict2kw_conv2d (mw['conv2.weight']) )
        PFLD_model.get_layer('bn2').set_weights ( tdict2kw_bn2d (mw, 'bn2') )

        for block_name in ['conv3_1', 'block3_2', 'block3_3', 'block3_4','block3_5','conv4_1','conv5_1','block5_2', \
                        'block5_3','block5_4','block5_5','block5_6','conv6_1']:
            PFLD_model.get_layer(block_name+'_conv0').set_weights ( tdict2kw_conv2d (mw[block_name+'.conv.0.weight']) )
            PFLD_model.get_layer(block_name+'_conv1').set_weights ( tdict2kw_bn2d (mw, block_name+'.conv.1') )
            PFLD_model.get_layer(block_name+'_conv3').set_weights ( tdict2kw_depconv2d (mw[block_name+'.conv.3.weight']) )
            PFLD_model.get_layer(block_name+'_conv4').set_weights ( tdict2kw_bn2d (mw, block_name+'.conv.4') )
            PFLD_model.get_layer(block_name+'_conv6').set_weights ( tdict2kw_conv2d (mw[block_name+'.conv.6.weight']) )
            PFLD_model.get_layer(block_name+'_conv7').set_weights ( tdict2kw_bn2d (mw, block_name+'.conv.7') )

        PFLD_model.get_layer('conv7_0').set_weights ( tdict2kw_conv2d (mw['conv7.0.weight']) )
        PFLD_model.get_layer('conv7_1').set_weights ( tdict2kw_bn2d (mw, 'conv7.1') )
        PFLD_model.get_layer('conv8').set_weights ( tdict2kw_conv2d (mw['conv8.weight'], mw['conv8.bias']) )

        PFLD_model.get_layer('fc').set_weights ( [ np.transpose(mw['fc.weight'].numpy(), [1,0] ), mw['fc.bias'] ] )
    except:
        pass

    PFLD_model.save_weights (r"D:\DevelopPython\test\PFLD.h5")
    PFLD_model_func = K.function (PFLD_model.inputs, PFLD_model.outputs)


    q, = PFLD_model_func([ image[None,...] ])
    """

    #image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    #w = np.transpose(w, [0,2,3,1])
    #diff = np.sum(np.abs(np.ndarray.flatten(q)-np.ndarray.flatten(w)))
    #print (f"====== diff {diff} =======")
    #lmrks_98 = lmrks_98[:,::-1]
    #lmrks_68 = LandmarksProcessor.convert_98_to_68 (lmrks_98)

    torch_pfld = PFLDInference()
    torch_pfld.load_state_dict(mw)
    torch_pfld.eval()

    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0
    image = cv2.resize (image, (112,112) )
    #image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image_torch = torch.autograd.Variable(torch.from_numpy( np.transpose(image[None,...], [0,3,1,2] ) ) )

    with torch.no_grad():
        _, w = torch_pfld( image_torch )
    w = w.cpu().numpy()



    lmrks_98 = w.reshape ( (-1,2) )*112
    for x, y in lmrks_98.astype(np.int):
        cv2.circle(image, (x, y), 1, (0,1,0) )

    #LandmarksProcessor.draw_landmarks (image, lmrks_68)

    #cv2.imshow ("1", image.astype(np.uint8) )
    cv2.imshow ("1", (image*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))





    """




    import code
    code.interact(local=dict(globals(), **locals()))

    import mxnet as mx
    sym = mx.symbol.load (r"D:\DevelopPython\test\al.json")

    module = mx.module.Module(symbol=sym,
                                data_names=['data'],
                                label_names=None,
                                context=mx.cpu(),
                                work_load_list=None)
    save_dict = mx.nd.load(r"D:\DevelopPython\test\al.params")

    import code
    code.interact(local=dict(globals(), **locals()))


    def process(w,h, data ):
        d = {}
        cur_lc = 0
        all_lines = []
        for s, pts_loop_ar in data:
            lines = []
            for pts, loop in pts_loop_ar:
                pts_len = len(pts)
                lines.append ( [ [ pts[i], pts[(i+1) % pts_len ] ]  for i in range(pts_len - (0 if loop else 1) ) ] )
            lines = np.concatenate (lines)

            lc = lines.shape[0]
            all_lines.append(lines)
            d[s] = cur_lc, cur_lc+lc
            cur_lc += lc
        all_lines = np.concatenate (all_lines, 0)

        #calculate signed distance for all points and lines
        line_count = all_lines.shape[0]
        pts_count = w*h

        all_lines = np.repeat ( all_lines[None,...], pts_count, axis=0 ).reshape ( (pts_count*line_count,2,2) )

        pts = np.empty( (h,w,line_count,2), dtype=np.float32 )
        pts[...,1] = np.arange(h)[:,None,None]
        pts[...,0] = np.arange(w)[:,None]
        pts = pts.reshape ( (h*w*line_count, -1) )

        a = all_lines[:,0,:]
        b = all_lines[:,1,:]
        pa = pts-a
        ba = b-a
        ph = np.clip ( np.einsum('ij,ij->i', pa, ba) / np.einsum('ij,ij->i', ba, ba), 0, 1 )
        dists = npla.norm ( pa - ba*ph[...,None], axis=1).reshape ( (h,w,line_count) )

        def get_dists(name, thickness=0):
            s,e = d[name]
            result = dists[...,s:e]
            if thickness != 0:
                result = np.abs(result)-thickness
            return np.min (result, axis=-1)

        return get_dists

    t = time.time()

    gdf = process ( 256,256,
                         (
                          ('x',  ( ( [ [0,0],[150,50],[30,180],[255,255] ], True), ) ),
                         )
                        )

    mask = gdf('x',3)
    mask = np.clip ( 1- ( np.sqrt( np.maximum(mask,0) ) / 5 ), 0, 1)
    # mask = 1-np.clip( np.cbrt(mask) / 15, 0, 1)


    def alpha_to_color (img_alpha, color):
        if len(img_alpha.shape) == 2:
            img_alpha = img_alpha[...,None]
        h,w,c = img_alpha.shape
        result = np.zeros( (h,w, len(color) ), dtype=np.float32 )
        result[:,:] = color

        return result * img_alpha

    mask = alpha_to_color(mask, (0,1,0) )


    print(f"time took {time.time() - t}")

    cv2.imshow ("1", (mask*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    ct_1_filepath = r'D:\DevelopPython\test\ct_00003.jpg'
    ct_1_img = cv2.imread(ct_1_filepath).astype(np.float32) / 255.0
    ct_1_img_shape = ct_1_img.shape
    ct_1_dflimg = DFLJPG.load ( ct_1_filepath)

    ct_2_filepath = r'D:\DevelopPython\test\ct_trg.jpg'
    ct_2_img = cv2.imread(ct_2_filepath).astype(np.float32) / 255.0
    ct_2_img_shape = ct_2_img.shape
    ct_2_dflimg = DFLJPG.load ( ct_2_filepath)

    result = cv2.bilateralFilter( ct_1_img , 0, 1000,1)


    #result = color_transfer_mkl ( ct_2_img, ct_1_img )



    #import code
    #code.interact(local=dict(globals(), **locals()))
    cv2.imshow ("1", (result*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    #t = time.time()
    ct_1_mask = LandmarksProcessor.get_image_hull_mask (ct_1_img_shape , ct_1_dflimg.get_landmarks() )
    ct_2_mask = LandmarksProcessor.get_image_hull_mask (ct_2_img_shape , ct_2_dflimg.get_landmarks() )

    #ct_1_cmask = ( LandmarksProcessor.get_cmask (ct_1_img_shape , ct_1_dflimg.get_landmarks() )  *255).astype(np.uint8)
    #ct_2_cmask = ( LandmarksProcessor.get_cmask (ct_2_img_shape , ct_2_dflimg.get_landmarks() )  *255).astype(np.uint8)
    #print (f"time took:{time.time()-t}")

    #LandmarksProcessor.draw_landmarks (ct_1_img, ct_1_dflimg.get_landmarks(), color=(0,255,0), transparent_mask=False, ie_polys=None)
    #cv2.imshow ("asd", (ct_1_cmask*255).astype(np.uint8) )
    #cv2.waitKey(0)
    #cv2.imshow ("asd", (ct_2_cmask*255).astype(np.uint8) )
    #cv2.waitKey(0)




    import ebsynth
    while True:

        mask = (np.ones_like(ct_2_img)*255).astype(np.uint8)

        mask[:,0:16,:] = 0
        mask[:,-16:0,:] = 0
        mask[0:16,:,:] = 0
        mask[-16:0,:,:] = 0
        t = time.time()
        img = imagelib.seamless_clone( ct_2_img.copy(), ct_1_img.copy(), ct_1_mask[...,0] )

        print (f"time took: {time.time()-t}")
        screen = np.concatenate ( (ct_1_img,  ct_2_img, img), axis=1)
        cv2.imshow ("1", (screen*255).astype(np.uint8) )
        cv2.waitKey(0)

    #import code
    #code.interact(local=dict(globals(), **locals()))
    import ebsynth
    while True:
        t = time.time()

        img = ebsynth.color_transfer(ct_2_img, ct_1_img)
        print (f"time took: {time.time()-t}")
        screen = np.concatenate ( (ct_1_img,  ct_2_img, img), axis=1)
        cv2.imshow ("1", screen )
        cv2.waitKey(0)

    import ebsynth
    while True:
        t = time.time()

        img = ebsynth.color_transfer(ct_1_img, ct_2_img)
        img2 = ebsynth.color_transfer(ct_1_img, ct_2_img, ct_1_cmask, ct_2_cmask)
        print (f"time took: {time.time()-t}")
        screen = np.concatenate ( (ct_1_img, ct_1_cmask, ct_2_img, ct_2_cmask, img, img2), axis=1)
        cv2.imshow ("asd", screen )
        cv2.waitKey(0)


    import code
    code.interact(local=dict(globals(), **locals()))



    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(cpu_only=True) ), locals(), globals() )

    class PixelShufflerTorch(KL.Layer):
        def __init__(self, size=(2, 2), data_format='channels_last', **kwargs):
            super(PixelShufflerTorch, self).__init__(**kwargs)
            self.data_format = data_format
            self.size = size

        def call(self, inputs):
            input_shape = K.shape(inputs)
            if K.int_shape(input_shape)[0] != 4:
                raise ValueError('Inputs should have rank 4; Received input shape:', str(K.int_shape(inputs)))

            batch_size, h, w, c = input_shape[0], input_shape[1], input_shape[2], K.int_shape(inputs)[-1]
            rh, rw = self.size
            oh, ow = h * rh, w * rw
            oc = c // (rh * rw)

            out = inputs
            out = K.permute_dimensions(out, (0, 3, 1, 2)) #NCHW

            out = K.reshape(out, (batch_size, oc, rh, rw, h, w))
            out = K.permute_dimensions(out, (0, 1, 4, 2, 5, 3))
            out = K.reshape(out, (batch_size, oc, oh, ow))

            out = K.permute_dimensions(out, (0, 2, 3, 1))
            return out

        def compute_output_shape(self, input_shape):
            if len(input_shape) != 4:
                raise ValueError('Inputs should have rank ' + str(4) + '; Received input shape:', str(input_shape))

            height = input_shape[1] * self.size[0] if input_shape[1] is not None else None
            width = input_shape[2] * self.size[1] if input_shape[2] is not None else None
            channels = input_shape[3] // self.size[0] // self.size[1]

            if channels * self.size[0] * self.size[1] != input_shape[3]:
                raise ValueError('channels of input and size are incompatible')

            return (input_shape[0],
                    height,
                    width,
                    channels)

        def get_config(self):
            config = {'size': self.size,
                    'data_format': self.data_format}
            base_config = super(PixelShufflerTorch, self).get_config()

            return dict(list(base_config.items()) + list(config.items()))

    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    model_weights = torch.load(r"D:\DevelopPython\test\RankSRGAN_NIQE.pth")

    def res_block(inp, name_prefix):
        x = inp
        x = Conv2D (ndf, kernel_size=3, strides=1, padding='same', activation="relu", name=name_prefix+"0")(x)
        x = Conv2D (ndf, kernel_size=3, strides=1, padding='same', name=name_prefix+"2")(x)
        return Add()([inp,x])

    RankSRGAN_Input = Input ( (None, None,3) )
    ndf = 64
    x = RankSRGAN_Input

    x = x0 = Conv2D (ndf, kernel_size=3, strides=1, padding='same', name="model0")(x)
    for i in range(16):
        x = res_block(x, "model1%.2d" %i )
    x = Conv2D (ndf, kernel_size=3, strides=1, padding='same', name="model1160")(x)
    x = Add()([x0,x])

    x = ReLU() ( PixelShufflerTorch() ( Conv2D (ndf*4, kernel_size=3, strides=1, padding='same', name="model2")(x) ) )
    x = ReLU() ( PixelShufflerTorch() ( Conv2D (ndf*4, kernel_size=3, strides=1, padding='same', name="model5")(x) ) )

    x = Conv2D (ndf, kernel_size=3, strides=1, padding='same', activation="relu", name="model8")(x)
    x = Conv2D (3,   kernel_size=3, strides=1, padding='same', name="model10")(x)
    RankSRGAN_model = Model(RankSRGAN_Input, x )

    RankSRGAN_model.get_layer("model0").set_weights (tdict2kw_conv2d (model_weights['model.0.weight'], model_weights['model.0.bias']))

    for i in range(16):
        RankSRGAN_model.get_layer("model1%.2d0" %i).set_weights (tdict2kw_conv2d (model_weights['model.1.sub.%d.res.0.weight' % i], model_weights['model.1.sub.%d.res.0.bias' % i]))
        RankSRGAN_model.get_layer("model1%.2d2" %i).set_weights (tdict2kw_conv2d (model_weights['model.1.sub.%d.res.2.weight' % i], model_weights['model.1.sub.%d.res.2.bias' % i]))

    RankSRGAN_model.get_layer("model1160").set_weights (tdict2kw_conv2d (model_weights['model.1.sub.16.weight'], model_weights['model.1.sub.16.bias']))
    RankSRGAN_model.get_layer("model2").set_weights (tdict2kw_conv2d (model_weights['model.2.weight'], model_weights['model.2.bias']))
    RankSRGAN_model.get_layer("model5").set_weights (tdict2kw_conv2d (model_weights['model.5.weight'], model_weights['model.5.bias']))
    RankSRGAN_model.get_layer("model8").set_weights (tdict2kw_conv2d (model_weights['model.8.weight'], model_weights['model.8.bias']))
    RankSRGAN_model.get_layer("model10").set_weights (tdict2kw_conv2d (model_weights['model.10.weight'], model_weights['model.10.bias']))

    RankSRGAN_model.save (r"D:\DevelopPython\test\RankSRGAN.h5")

    RankSRGAN_model_func = K.function (RankSRGAN_model.inputs, RankSRGAN_model.outputs)

    image = cv2.imread(r'D:\DevelopPython\test\00002.jpg').astype(np.float32) / 255.0

    q, = RankSRGAN_model_func([ image[None,...] ])

    cv2.imshow ("", np.clip ( q[0]*255, 0, 255).astype(np.uint8) )
    cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))



    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0
    image_shape = image.shape

    def apply_motion_blur(image, size, angle):
        k = np.zeros((size, size), dtype=np.float32)
        k[ (size-1)// 2 , :] = np.ones(size, dtype=np.float32)
        k = cv2.warpAffine(k, cv2.getRotationMatrix2D( (size / 2 -0.5 , size / 2 -0.5 ) , angle, 1.0), (size, size) )
        k = k * ( 1.0 / np.sum(k) )
        return cv2.filter2D(image, -1, k)

    for i in range(0, 9999):
        img = np.clip ( apply_motion_blur(image, 15, i % 360), 0, 1 )

        cv2.imshow ("", ( img*255).astype(np.uint8) )
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(cpu_only=True) ), locals(), globals() )
    PMLTile = nn.PMLTile
    PMLK = nn.PMLK

    def rgb_to_lab(inp):
        rgb_pixels =                   (inp / 12.92 * K.cast(inp <= 0.04045, dtype=K.floatx() ) ) \
               + K.pow( (inp + 0.055) / 1.055, 2.4) * K.cast(inp > 0.04045 , dtype=K.floatx() )

        xyz_pixels = K.dot(rgb_pixels,  K.constant( np.array([
                                        #    X        Y          Z
                                        [0.412453, 0.212671, 0.019334], # R
                                        [0.357580, 0.715160, 0.119193], # G
                                        [0.180423, 0.072169, 0.950227], # B
                                     ]))) / K.constant([0.950456, 1.0, 1.088754])

        fxfyfz_pixels = (xyz_pixels * 7.787 + 16/116 ) * K.cast(xyz_pixels <= 0.008856, dtype=K.floatx() ) \
                              + K.pow(xyz_pixels, 1/3) * K.cast(xyz_pixels > 0.008856 , dtype=K.floatx() )

        x = K.dot(fxfyfz_pixels, K.constant( np.array([
                                        #  l       a       b
                                        [  0.0,  500.0,    0.0], # fx
                                        [116.0, -500.0,  200.0], # fy
                                        [  0.0,    0.0, -200.0], # fz
                                    ]))) + K.constant([-16.0, 0.0, 0.0])

        x = K.round ( x )
        return x

    def lab_to_rgb(inp):
        fxfyfz_pixels = K.dot(inp + K.constant([16.0, 0.0, 0.0]), K.constant(np.array([
                                        #   fx      fy        fz
                                        [1/116.0, 1/116.0,  1/116.0], # l
                                        [1/500.0,     0.0,      0.0], # a
                                        [    0.0,     0.0, -1/200.0], # b
                                    ])))

        xyz_pixels = ( ( (fxfyfz_pixels - 16/116 ) / 7.787 ) * K.cast(fxfyfz_pixels <= 6/29, dtype=K.floatx() ) \
                                   + K.pow(fxfyfz_pixels, 3) * K.cast(fxfyfz_pixels > 6/29, dtype=K.floatx() )  \
                     ) * K.constant([0.950456, 1.0, 1.088754])

        rgb_pixels = K.dot(xyz_pixels, K.constant(np.array([
                            #     r           g          b
                            [ 3.2404542, -0.9692660,  0.0556434], # x
                            [-1.5371385,  1.8760108, -0.2040259], # y
                            [-0.4985314,  0.0415560,  1.0572252], # z
                        ])))
        rgb_pixels = K.clip(rgb_pixels, 0.0, 1.0)

        return                          (rgb_pixels * 12.92 * K.cast(rgb_pixels <= 0.0031308, dtype=K.floatx() ) ) \
             + ( (K.pow(rgb_pixels, 1/2.4) * 1.055) - 0.055) * K.cast(rgb_pixels > 0.0031308, dtype=K.floatx() )

    def rct_flow(img_src_t, img_trg_t):
        if len(K.int_shape(img_src_t)) != len(K.int_shape(img_trg_t)):
            raise ValueError( len(img_src_t.shape) != len(img_trg_t.shape) )


        initial_shape = K.shape(img_src_t)
        h,w,c = K.int_shape(img_src_t)[-3::]

        img_src_t = K.reshape ( img_src_t, (-1,h,w,c) )
        img_trg_t = K.reshape ( img_trg_t, (-1,h,w,c) )



        img_src_lab_t = rgb_to_lab(img_src_t)
        img_src_lab_L_t = img_src_lab_t[...,0:1]
        img_src_lab_a_t = img_src_lab_t[...,1:2]
        img_src_lab_b_t = img_src_lab_t[...,2:3]

        img_src_lab_L_mean_t = K.mean(img_src_lab_L_t, axis=(-1,-2,-3), keepdims=True )
        img_src_lab_L_std_t  = K.std(img_src_lab_L_t, axis=(-1,-2,-3), keepdims=True )
        img_src_lab_a_mean_t = K.mean(img_src_lab_a_t, axis=(-1,-2,-3), keepdims=True )
        img_src_lab_a_std_t  = K.std(img_src_lab_a_t, axis=(-1,-2,-3), keepdims=True )
        img_src_lab_b_mean_t = K.mean(img_src_lab_b_t, axis=(-1,-2,-3), keepdims=True )
        img_src_lab_b_std_t  = K.std(img_src_lab_b_t, axis=(-1,-2,-3), keepdims=True )

        img_trg_lab_t = rgb_to_lab(img_trg_t)
        img_trg_lab_L_t = img_trg_lab_t[...,0:1]
        img_trg_lab_a_t = img_trg_lab_t[...,1:2]
        img_trg_lab_b_t = img_trg_lab_t[...,2:3]
        img_trg_lab_L_mean_t = K.mean(img_trg_lab_L_t, axis=(-1,-2,-3), keepdims=True )
        img_trg_lab_L_std_t  = K.std(img_trg_lab_L_t, axis=(-1,-2,-3), keepdims=True )
        img_trg_lab_a_mean_t = K.mean(img_trg_lab_a_t, axis=(-1,-2,-3), keepdims=True )
        img_trg_lab_a_std_t  = K.std(img_trg_lab_a_t, axis=(-1,-2,-3), keepdims=True )
        img_trg_lab_b_mean_t = K.mean(img_trg_lab_b_t, axis=(-1,-2,-3), keepdims=True )
        img_trg_lab_b_std_t  = K.std(img_trg_lab_b_t, axis=(-1,-2,-3), keepdims=True )

        img_new_lab_L_t = (img_src_lab_L_std_t / img_trg_lab_L_std_t)*(img_trg_lab_L_t-img_trg_lab_L_mean_t) + img_src_lab_L_mean_t
        img_new_lab_a_t = (img_src_lab_a_std_t / img_trg_lab_a_std_t)*(img_trg_lab_a_t-img_trg_lab_a_mean_t) + img_src_lab_a_mean_t
        img_new_lab_b_t = (img_src_lab_b_std_t / img_trg_lab_b_std_t)*(img_trg_lab_b_t-img_trg_lab_b_mean_t) + img_src_lab_b_mean_t

        img_new_t = lab_to_rgb( K.concatenate ( [img_new_lab_L_t, img_new_lab_a_t, img_new_lab_b_t], -1) )

        img_new_t = K.reshape ( img_new_t, initial_shape )

        return img_new_t


    # class ImagePatches(PMLTile.Operation):
    #     def __init__(self, images, ksizes, strides, rates=(1,1,1,1), padding="VALID"):
    #         """
    #         Compatible to tensorflow.extract_image_patches.
    #         Extract patches from images and put them in the "depth" output dimension.
    #         Args:
    #             images: A tensor with a shape of [batch, rows, cols, depth]
    #             ksizes: The size of the oatches with a shape of [1, patch_rows, patch_cols, 1]
    #             strides: How far the center of two patches are in the image with a shape of [1, stride_rows, stride_cols, 1]
    #             rates: How far two consecutive pixel are in the input. Equivalent to dilation. Expect shape of [1, rate_rows, rate_cols, 1]
    #             padding: A string of "VALID" or "SAME" defining padding.

    #         Does not work with symbolic height and width.
    #         """
    #         i_shape = images.shape.dims
    #         patch_row_eff = ksizes[1] + ((ksizes[1] - 1) * (rates[1] -1))
    #         patch_col_eff = ksizes[2] + ((ksizes[2] - 1) * (rates[2] -1))

    #         if padding.upper() == "VALID":
    #             out_rows = math.ceil((i_shape[1] - patch_row_eff + 1.) / float(strides[1]))
    #             out_cols = math.ceil((i_shape[2] - patch_col_eff + 1.) / float(strides[2]))
    #             pad_str = "PAD = I;"
    #         else:
    #             out_rows = math.ceil( i_shape[1] / float(strides[1]) )
    #             out_cols = math.ceil( i_shape[2] / float(strides[2]) )
    #             dim_calc = "NY={NY}; NX={NX};".format(NY=out_rows, NX=out_cols)
    #             pad_top = max(0, ( (out_rows - 1) * strides[1] + patch_row_eff - i_shape[1] ) // 2)
    #             pad_left = max(0, ( (out_cols - 1) * strides[2] + patch_col_eff - i_shape[2] ) // 2)
    #             # we simply assume padding right == padding left + 1 (same for top/down).
    #             # This might lead to us padding more as we would need but that won't matter.
    #             # TF splits padding between both sides so left_pad +1 should keep us on the safe side.
    #             pad_str = """PAD[b, y, x, d : B, Y + {PT} * 2 + 1, X + {PL} * 2 + 1, D] =
    #                         =(I[b, y - {PT}, x - {PL}, d]);""".format(PT=pad_top, PL=pad_left)

    #         o_shape = (i_shape[0], out_rows, out_cols, ksizes[1]*ksizes[2]*i_shape[-1])
    #         code = """function (I[B,Y,X,D]) -> (O) {{
    #                     {PAD}
    #                     TMP[b, ny, nx, y, x, d: B, {NY}, {NX}, {KY}, {KX}, D] =
    #                         =(PAD[b, ny * {SY} + y * {RY}, nx * {SX} + x * {RX}, d]);
    #                     O = reshape(TMP, B, {NY}, {NX}, {KY} * {KX} * D);
    #                 }}
    #         """.format(
    #             PAD=pad_str,
    #             NY=out_rows, NX=out_cols,
    #             KY=ksizes[1], KX=ksizes[2],
    #             SY=strides[1], SX=strides[2],
    #             RY=rates[1], RX=rates[2]
    #         )
    #         super(ImagePatches, self).__init__(code,
    #                 [('I', images),],
    #             [('O', PMLTile.Shape(images.shape.dtype, o_shape))])

    img_src = cv2.imread(r'D:\DevelopPython\test\ct_src.jpg').astype(np.float32) / 255.0
    img_src = np.expand_dims (img_src, 0)
    img_src_shape = img_src.shape

    img_trg = cv2.imread(r'D:\DevelopPython\test\ct_trg.jpg').astype(np.float32) / 255.0
    img_trg = np.expand_dims (img_trg, 0)
    img_trg_shape = img_trg.shape

    img_src_t = Input ( img_src_shape[1:] )
    img_trg_t = Input ( img_src_shape[1:] )

    img_rct_t = rct_flow (img_src_t, img_trg_t)

    img_rct = K.function ( [img_src_t, img_trg_t], [ img_rct_t ]) ( [img_src[...,::-1], img_trg[...,::-1]]) [0][0][...,::-1]


    img_rct_true = imagelib.reinhard_color_transfer ( np.clip( (img_trg[0]*255).astype(np.uint8), 0, 255),
                                                      np.clip( (img_src[0]*255).astype(np.uint8), 0, 255) )

    img_rct_true = img_rct_true / 255.0

    print("diff ", np.sum(np.abs(img_rct-img_rct_true)) )

    cv2.imshow ("", ( img_rct*255).astype(np.uint8) )
    cv2.waitKey(0)
    cv2.imshow ("", ( img_rct_true*255).astype(np.uint8) )
    cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))


    wnd_size = 15#img_src.shape[1] // 8 - 1
    pad_size = wnd_size // 2
    sh = img_src.shape[1] + pad_size*2

    step_size = 1
    k = (sh-wnd_size) // step_size + 1

    img_src_padded_t = K.spatial_2d_padding (img_src_t, ((pad_size,pad_size), (pad_size,pad_size)) )
    img_trg_padded_t = K.spatial_2d_padding (img_trg_t, ((pad_size,pad_size), (pad_size,pad_size)) )
    #ImagePatches.function
    img_src_patches_t = nn.tf.extract_image_patches ( img_src_padded_t, [1,k,k,1], [1,1,1,1], [1,step_size,step_size,1], "VALID")
    img_trg_patches_t = nn.tf.extract_image_patches ( img_trg_padded_t, [1,k,k,1], [1,1,1,1], [1,step_size,step_size,1], "VALID")


    img_src_patches_t = \
    K.concatenate ([ K.expand_dims( K.permute_dimensions ( img_src_patches_t[...,2::3], (0,3,1,2) ), -1),
                     K.expand_dims( K.permute_dimensions ( img_src_patches_t[...,1::3], (0,3,1,2) ), -1),
                     K.expand_dims( K.permute_dimensions ( img_src_patches_t[...,0::3], (0,3,1,2) ), -1) ], -1 )

    img_trg_patches_t = \
    K.concatenate ([ K.expand_dims( K.permute_dimensions ( img_trg_patches_t[...,2::3], (0,3,1,2) ), -1),
                     K.expand_dims( K.permute_dimensions ( img_trg_patches_t[...,1::3], (0,3,1,2) ), -1),
                     K.expand_dims( K.permute_dimensions ( img_trg_patches_t[...,0::3], (0,3,1,2) ), -1) ], -1 )

    #img_src_patches_lab_t = bgr_to_lab(img_src_patches_t)
    #img_src_patches_lab = K.function ( [img_src_t], [ img_src_patches_lab_t ]) ([img_src]) [0][0]

    img_rct_patches_t = rct_flow (img_src_patches_t, img_trg_patches_t)

    img_rct_t = K.reshape ( img_rct_patches_t[...,pad_size,pad_size,:], (-1,256,256,3) )

    img_rct = K.function ( [img_src_t, img_trg_t], [ img_rct_t ]) ( [img_src, img_trg]) [0][0][...,::-1]

    #import code
    #code.interact(local=dict(globals(), **locals()))

    #for i in range( img_rct.shape[0] ):
    cv2.imshow ("", ( img_rct*255).astype(np.uint8) )
    cv2.waitKey(0)



    #cv2.imshow ("", (img_new*255).astype(np.uint8) )
    #cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    bgr_to_lab_f = K.function ( [image_tensor], [ image_lab_t ])
    lab_to_bgr_f = K.function ( [image_tensor], [ lab_to_bgr(image_tensor) ])

    img_src_lab = bgr_to_lab_f( [img_src[...,::-1]] )
    img_src_lab_bgr, = lab_to_bgr_f( [img_src_lab] )

    diff = np.sum ( np.abs(img_src-img_src_lab_bgr[...,::-1] ) )
    print ("bgr->lab->bgr diff ", diff)

    #image_cv_lab = cv2.cvtColor( img_src[0], cv2.COLOR_BGR2LAB)
    #print ("lab and cv lab diff ", np.sum(np.abs(image_lab[0].astype(np.int8)-image_cv_lab.astype(np.int8))) )
    #print ("lab and cv lab diff ", np.sum(np.abs(image_lab[0]-image_cv_lab)) )

    #cv2.imshow ("", image_bgr.astype(np.uint8) )
    #cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    ###########
    """
    img_src_lab_t = bgr_to_lab(img_src_t)
    img_src_lab_L_t = img_src_lab_t[...,0:1]
    img_src_lab_a_t = img_src_lab_t[...,1:2]
    img_src_lab_b_t = img_src_lab_t[...,2:3]
    img_src_lab_L_mean_t = K.mean(img_src_lab_L_t)
    img_src_lab_L_std_t = K.std(img_src_lab_L_t)
    img_src_lab_a_mean_t = K.mean(img_src_lab_a_t)
    img_src_lab_a_std_t = K.std(img_src_lab_a_t)
    img_src_lab_b_mean_t = K.mean(img_src_lab_b_t)
    img_src_lab_b_std_t = K.std(img_src_lab_b_t)

    img_trg_lab_t = bgr_to_lab(img_trg_t)
    img_trg_lab_L_t = img_trg_lab_t[...,0:1]
    img_trg_lab_a_t = img_trg_lab_t[...,1:2]
    img_trg_lab_b_t = img_trg_lab_t[...,2:3]
    img_trg_lab_L_mean_t = K.mean(img_trg_lab_L_t)
    img_trg_lab_L_std_t = K.std(img_trg_lab_L_t)
    img_trg_lab_a_mean_t = K.mean(img_trg_lab_a_t)
    img_trg_lab_a_std_t = K.std(img_trg_lab_a_t)
    img_trg_lab_b_mean_t = K.mean(img_trg_lab_b_t)
    img_trg_lab_b_std_t = K.std(img_trg_lab_b_t)
    img_new_lab_L_t = (img_src_lab_L_std_t / img_trg_lab_L_std_t)*(img_trg_lab_L_t-img_trg_lab_L_mean_t) + img_src_lab_L_mean_t
    img_new_lab_a_t = (img_src_lab_a_std_t / img_trg_lab_a_std_t)*(img_trg_lab_a_t-img_trg_lab_a_mean_t) + img_src_lab_a_mean_t
    img_new_lab_b_t = (img_src_lab_b_std_t / img_trg_lab_b_std_t)*(img_trg_lab_b_t-img_trg_lab_b_mean_t) + img_src_lab_b_mean_t
    img_new_t = lab_to_bgr( K.concatenate ( [img_new_lab_L_t, img_new_lab_a_t, img_new_lab_b_t], -1) )
    rct_f = K.function ( [img_src_t, img_trg_t], [ img_new_t ])
    img_new, = rct_f([ img_src[...,::-1], img_trg[...,::-1]  ])[0][...,::-1]
    """

    """
    def bgr_to_lab(inp):
        rgb_pixels =                   (inp / 12.92 * K.cast(inp <= 0.04045, dtype=K.floatx() ) ) \
               + K.pow( (inp + 0.055) / 1.055, 2.4) * K.cast(inp > 0.04045 , dtype=K.floatx() )

        xyz_pixels = K.dot(rgb_pixels,  K.constant( np.array([
                                        #    X        Y          Z
                                        [0.412453, 0.212671, 0.019334], # R
                                        [0.357580, 0.715160, 0.119193], # G
                                        [0.180423, 0.072169, 0.950227], # B
                                     ]))) / K.constant([0.950456, 1.0, 1.088754])

        fxfyfz_pixels = (xyz_pixels * 7.787 + 16/116 ) * K.cast(xyz_pixels <= 0.008856, dtype=K.floatx() ) \
                              + K.pow(xyz_pixels, 1/3) * K.cast(xyz_pixels > 0.008856 , dtype=K.floatx() )

        return K.dot(fxfyfz_pixels, K.constant( np.array([
                                        #  l       a       b
                                        [  0.0,  500.0,    0.0], # fx
                                        [116.0, -500.0,  200.0], # fy
                                        [  0.0,    0.0, -200.0], # fz
                                    ]))) + K.constant([-16.0, 0.0, 0.0])

    def lab_to_bgr(inp):
        fxfyfz_pixels = K.dot(inp + K.constant([16.0, 0.0, 0.0]), K.constant(np.array([
                                        #   fx      fy        fz
                                        [1/116.0, 1/116.0,  1/116.0], # l
                                        [1/500.0,     0.0,      0.0], # a
                                        [    0.0,     0.0, -1/200.0], # b
                                    ])))

        xyz_pixels = ( ( (fxfyfz_pixels - 16/116 ) / 7.787 ) * K.cast(fxfyfz_pixels <= 6/29, dtype=K.floatx() ) \
                                   + K.pow(fxfyfz_pixels, 3) * K.cast(fxfyfz_pixels > 6/29, dtype=K.floatx() )  \
                     ) * K.constant([0.950456, 1.0, 1.088754])

        rgb_pixels = K.dot(xyz_pixels, K.constant(np.array([
                            #     r           g          b
                            [ 3.2404542, -0.9692660,  0.0556434], # x
                            [-1.5371385,  1.8760108, -0.2040259], # y
                            [-0.4985314,  0.0415560,  1.0572252], # z
                        ])))
        rgb_pixels = K.clip(rgb_pixels, 0.0, 1.0)

        return                          (rgb_pixels * 12.92 * K.cast(rgb_pixels <= 0.0031308, dtype=K.floatx() ) ) \
             + ( (K.pow(rgb_pixels, 1/2.4) * 1.055) - 0.055) * K.cast(rgb_pixels > 0.0031308, dtype=K.floatx() )
    """

    ######
    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=0) ), locals(), globals() )

    shape = (64, 64, 3)
    def encflow(x):
        x = keras.layers.Conv2D(128, 5, strides=2, padding="same")(x)
        x = keras.layers.Conv2D(256, 5, strides=2, padding="same")(x)
        x = keras.layers.Dense(3)(keras.layers.Flatten()(x))
        return x

    def modelify(model_functor):
        def func(tensor):
            return keras.models.Model (tensor, model_functor(tensor))
        return func

    encoder = modelify (encflow)( keras.Input(shape) )

    inp = x = keras.Input(shape)
    code_t = encoder(x)
    loss = K.mean(code_t)

    train_func = K.function ([inp],[loss], keras.optimizers.Adam().get_updates(loss, encoder.trainable_weights) )
    train_func ([ np.zeros ( (1, 64, 64, 3) ) ])

    import code
    code.interact(local=dict(globals(), **locals()))

    ###########

    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32)# / 255.0
    image = (image - image.mean( (0,1)) ) / image.std( (0,1) )
    cv2.imshow ("", ((image +127)).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    ###########

    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config() ), locals(), globals() )

    def gaussian_blur(radius=2.0):
        def gaussian(x, mu, sigma):
            return np.exp(-(float(x) - float(mu)) ** 2 / (2 * sigma ** 2))

        def make_kernel(sigma):
            kernel_size = max(3, int(2 * 2 * sigma + 1))
            mean = np.floor(0.5 * kernel_size)
            kernel_1d = np.array([gaussian(x, mean, sigma) for x in range(kernel_size)])
            np_kernel = np.outer(kernel_1d, kernel_1d).astype(dtype=K.floatx())
            kernel = np_kernel / np.sum(np_kernel)
            return kernel

        gauss_kernel = make_kernel(radius)
        gauss_kernel = gauss_kernel[:, :,np.newaxis, np.newaxis]

        def func(input):
            inputs = [ input[:,:,:,i:i+1]  for i in range( K.int_shape( input )[-1] ) ]

            outputs = []
            for i in range(len(inputs)):
                outputs += [ K.conv2d( inputs[i] , K.constant(gauss_kernel) , strides=(1,1), padding="same") ]

            return K.concatenate (outputs, axis=-1)
        return func

    def style_loss_test(gaussian_blur_radius=0.0, loss_weight=1.0, wnd_size=0, step_size=1):
        if gaussian_blur_radius > 0.0:
            gblur = gaussian_blur(gaussian_blur_radius)

        def bgr_to_lab(inp):
            linear_mask = K.cast(inp <= 0.04045, dtype=K.floatx() )
            exponential_mask = K.cast(inp > 0.04045, dtype=K.floatx() )
            rgb_pixels = (inp / 12.92 * linear_mask) + (((inp + 0.055) / 1.055) ** 2.4) * exponential_mask
            rgb_to_xyz = K.constant([
                #    X        Y          Z
                [0.180423, 0.072169, 0.950227], # B
                [0.357580, 0.715160, 0.119193], # G
                [0.412453, 0.212671, 0.019334], # R
            ])

            xyz_pixels = K.dot(rgb_pixels, rgb_to_xyz)
            xyz_normalized_pixels = xyz_pixels * [1/0.950456, 1.0, 1/1.088754]

            epsilon = 6/29
            linear_mask = K.cast(xyz_normalized_pixels <= (epsilon**3), dtype=K.floatx() )
            exponential_mask = K.cast(xyz_normalized_pixels > (epsilon**3), dtype=K.floatx() )
            fxfyfz_pixels = (xyz_normalized_pixels / (3 * epsilon**2) + 4/29) * linear_mask + (xyz_normalized_pixels ** (1/3)) * exponential_mask

            # convert to lab
            fxfyfz_to_lab = K.constant([
                #  l       a       b
                [  0.0,  500.0,    0.0], # fx
                [116.0, -500.0,  200.0], # fy
                [  0.0,    0.0, -200.0], # fz
            ])
            lab = K.dot(fxfyfz_pixels, fxfyfz_to_lab) + K.constant([-16.0, 0.0, 0.0])
            return lab[...,0:1], lab[...,1:2], lab[...,2:3]

        def sd(content, style, loss_weight):
            content_nc = K.int_shape(content)[-1]
            style_nc = K.int_shape(style)[-1]
            if content_nc != style_nc:
                raise Exception("style_loss() content_nc != style_nc")

            cl,ca,cb = bgr_to_lab(content)
            sl,sa,sb = bgr_to_lab(style)
            axes = [1,2]
            cl_mean, cl_std = K.mean(cl, axis=axes, keepdims=True), K.var(cl, axis=axes, keepdims=True)+ 1e-5
            ca_mean, ca_std = K.mean(ca, axis=axes, keepdims=True), K.var(ca, axis=axes, keepdims=True)+ 1e-5
            cb_mean, cb_std = K.mean(cb, axis=axes, keepdims=True), K.var(cb, axis=axes, keepdims=True)+ 1e-5

            sl_mean, sl_std = K.mean(sl, axis=axes, keepdims=True), K.var(sl, axis=axes, keepdims=True)+ 1e-5
            sa_mean, sa_std = K.mean(sa, axis=axes, keepdims=True), K.var(sa, axis=axes, keepdims=True)+ 1e-5
            sb_mean, sb_std = K.mean(sb, axis=axes, keepdims=True), K.var(sb, axis=axes, keepdims=True)+ 1e-5


            loss = K.mean( K.square( cl - ( (sl - sl_mean) * ( cl_std / sl_std ) + cl_mean ) ) ) + \
                    K.mean( K.square( ca - ( (sa - sa_mean) * ( ca_std / sa_std ) + ca_mean ) ) ) + \
                    K.mean( K.square( cb - ( (sb - sb_mean) * ( cb_std / sb_std ) + cb_mean ) ) )


            #import code
            #code.interact(local=dict(globals(), **locals()))


            return loss * ( loss_weight / float(content_nc) )

        def func(target, style):
            if wnd_size == 0:
                if gaussian_blur_radius > 0.0:
                    return sd( gblur(target), gblur(style), loss_weight=loss_weight)
                else:
                    return sd( target, style, loss_weight=loss_weight )
        return func

    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0
    image2 = cv2.imread(r'D:\DevelopPython\test\00000.jpg').astype(np.float32) / 255.0

    inp_t = Input ( (256,256,3) )
    inp2_t = Input ( (256,256,3) )

    loss_t = style_loss_test(gaussian_blur_radius=16.0, loss_weight=0.01 )(inp_t, inp2_t)

    loss, = K.function ([inp_t,inp2_t], [loss_t]) ( [ image[np.newaxis,...], image2[np.newaxis,...] ] )



    import code
    code.interact(local=dict(globals(), **locals()))


    ###########

    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0

    from core.imagelib import LinearMotionBlur

    image = LinearMotionBlur(image, 5, 135)

    cv2.imshow("", (image*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    ###########


    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=0) ), locals(), globals() )

    from core.imagelib import DCSCN

    dc = DCSCN()

    image = cv2.imread(r'D:\DevelopPython\test\sr1.png').astype(np.float32) / 255.0

    image_up = dc.upscale(image)
    cv2.imwrite (r'D:\DevelopPython\test\sr1_result.png', (image_up*255).astype(np.uint8) )


    import code
    code.interact(local=dict(globals(), **locals()))

    ###########
    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config(force_gpu_idx=0) ), locals(), globals() )
    PMLTile = nn.PMLTile
    PMLK = nn.PMLK

    shape = (64, 64, 3)
    def encflow(x):
        x = LeakyReLU()(keras.layers.Conv2D(128, 5, strides=2, padding="same")(x))
        x = keras.layers.Conv2D(256, 5, strides=2, padding="same")(x)
        x = keras.layers.Conv2D(512, 5, strides=2, padding="same")(x)
        x = keras.layers.Conv2D(1024,5, strides=2, padding="same")(x)
        x = keras.layers.Dense(64)(keras.layers.Flatten()(x))
        x = keras.layers.Dense(4 * 4 * 1024)(x)
        x = keras.layers.Reshape((4, 4, 1024))(x)
        x = keras.layers.Conv2DTranspose(512, 3, strides=2, padding="same")(x)
        return x

    def decflow(x):
        x = x[0]
        x = LeakyReLU()(keras.layers.Conv2DTranspose(512, 3, strides=2, padding="same")(x))
        x = keras.layers.Conv2DTranspose(256, 3, strides=2, padding="same")(x)
        x = keras.layers.Conv2DTranspose(128, 3, strides=2, padding="same")(x)
        x = keras.layers.Conv2D(3, 5, strides=1, padding="same")(x)
        return x

    def modelify(model_functor):
        def func(tensor):
            return keras.models.Model (tensor, model_functor(tensor))
        return func

    encoder = modelify (encflow)( keras.Input(shape) )
    decoder1 = modelify (decflow)( [ Input(K.int_shape(x)[1:]) for x in encoder.outputs ] )
    decoder2 = modelify (decflow)( [ Input(K.int_shape(x)[1:]) for x in encoder.outputs ] )

    inp = x = keras.Input(shape)
    code = encoder(x)
    x1 = decoder1(code)
    x2 = decoder2(code)

    loss = K.mean(K.square(inp-x1))+K.mean(K.square(inp-x2))
    train_func = K.function ([inp],[loss], keras.optimizers.Adam().get_updates(loss, encoder.trainable_weights+decoder1.trainable_weights+decoder2.trainable_weights) )
    view_func1 = K.function ([inp],[x1])
    view_func2 = K.function ([inp],[x2])

    for i in range(100):
        print("Loop %i" % i)
        data = np.zeros ( (1, 64, 64, 3) )
        train_func ( [data])
        view_func1 ([data])
        view_func2 ([data])
        print("Saving weights")
        encoder.save_weights(r"D:\DevelopPython\test\testweights.h5")
        decoder1.save_weights(r"D:\DevelopPython\test\testweights1.h5")
        decoder2.save_weights(r"D:\DevelopPython\test\testweights2.h5")

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    exec( nn.import_all( device_config=nn.device.Config() ), locals(), globals() )
    PMLTile = nn.PMLTile
    PMLK = nn.PMLK

    import tensorflow as tf
    tfkeras = tf.keras
    tfK = tfkeras.backend
    lin = np.broadcast_to( np.linspace(1,10,10), (10,10) )

    #a = np.broadcast_to ( np.concatenate( [np.linspace(1,4,4), np.linspace(5,1,5)] ), (9,9) )
    #a = (a + a.T)-1
    #a = a[np.newaxis,:,:,np.newaxis]

    class ReflectionPadding2D():
        class TileOP(PMLTile.Operation):
            def __init__(self, input, h_pad, w_pad):
                if K.image_data_format() == 'channels_last':
                    if input.shape.ndims == 4:
                        H, W = input.shape.dims[1:3]
                        if (type(H) == int and h_pad >= H) or \
                        (type(W) == int and w_pad >= W):
                            raise ValueError("Paddings must be less than dimensions.")

                        c = """ function (I[B, H, W, C] ) -> (O) {{
                                WE = W + {w_pad}*2;
                                HE = H + {h_pad}*2;
                            """.format(h_pad=h_pad, w_pad=w_pad)
                        if w_pad > 0:
                            c += """
                                LEFT_PAD [b, h, w , c : B, H, WE, C ] = =(I[b, h, {w_pad}-w,            c]), w < {w_pad} ;
                                HCENTER  [b, h, w , c : B, H, WE, C ] = =(I[b, h, w-{w_pad},            c]), w < W+{w_pad}-1 ;
                                RIGHT_PAD[b, h, w , c : B, H, WE, C ] = =(I[b, h, 2*W - (w-{w_pad}) -2, c]);
                                LCR = LEFT_PAD+HCENTER+RIGHT_PAD;
                            """.format(h_pad=h_pad, w_pad=w_pad)
                        else:
                            c += "LCR = I;"

                        if h_pad > 0:
                            c += """
                                TOP_PAD   [b, h, w , c : B, HE, WE, C ] = =(LCR[b, {h_pad}-h,            w, c]), h < {h_pad};
                                VCENTER   [b, h, w , c : B, HE, WE, C ] = =(LCR[b, h-{h_pad},            w, c]), h < H+{h_pad}-1 ;
                                BOTTOM_PAD[b, h, w , c : B, HE, WE, C ] = =(LCR[b, 2*H - (h-{h_pad}) -2, w, c]);
                                TVB = TOP_PAD+VCENTER+BOTTOM_PAD;
                            """.format(h_pad=h_pad, w_pad=w_pad)
                        else:
                            c += "TVB = LCR;"

                        c += "O = TVB; }"

                        inp_dims = input.shape.dims
                        out_dims = (inp_dims[0], inp_dims[1]+h_pad*2, inp_dims[2]+w_pad*2, inp_dims[3])
                    else:
                        raise NotImplemented
                else:
                    raise NotImplemented

                super(ReflectionPadding2D.TileOP, self).__init__(c, [('I', input) ],
                        [('O', PMLTile.Shape(input.shape.dtype, out_dims ) )])

        def __init__(self, h_pad, w_pad):
            self.h_pad, self.w_pad = h_pad, w_pad

        def __call__(self, inp):
            return ReflectionPadding2D.TileOP.function(inp, self.h_pad, self.w_pad)

    sh_w = 9
    sh_h = 9
    sh = (1,sh_h,sh_w,1)
    w_pad, h_pad = 8,8


    t1 = tfK.placeholder (sh )
    t2 = tf.pad(t1, [ [0,0], [h_pad,h_pad], [w_pad,w_pad], [0,0] ], 'REFLECT')

    pt1 = K.placeholder (sh )
    pt2 = ReflectionPadding2D(h_pad, w_pad )(pt1)

    tfunc = tfK.function ([t1],[t2])
    ptfunc = K.function([pt1],[pt2])

    for i in range(100):
        a = np.random.uniform( size=sh)
        # a = np.broadcast_to ( np.concatenate( [np.linspace(1,4,4), np.linspace(5,1,5)] ), (9,9) )
        # a = np.broadcast_to (np.linspace(1,9,9), (9,9) )
        # a = (a + a.T)-1
        # a = a[np.newaxis,:,:,np.newaxis]

        t = tfunc([a]) [0][0,:,:,0]
        pt = ptfunc ([a])[0][0,:,:,0]
        if np.allclose(t, pt):
            print ("all_close = True")
        else:
            print ("all_close = False\r\n")
            print(t,"")
            print(pt)
    import code
    code.interact(local=dict(globals(), **locals()))

    image = cv2.imread(r'D:\DevelopPython\test\00000.png').astype(np.float32) / 255.0
    image = np.expand_dims (image, 0)
    image_shape = image.shape

    image2 = cv2.imread(r'D:\DevelopPython\test\00001.png').astype(np.float32) / 255.0
    image2 = np.expand_dims (image2, 0)
    image2_shape = image2.shape


    # class ReflectionPadding2D():
    #     def __init__(self, h_pad, w_pad):
    #         self.h_pad, self.w_pad = h_pad, w_pad

    #     def __call__(self, inp):
    #         h_pad, w_pad = self.h_pad, self.w_pad
    #         if K.image_data_format() == 'channels_last':
    #             if inp.shape.ndims == 4:
    #                 w = K.concatenate ([ inp[:,:,w_pad:0:-1,:],
    #                                      inp,
    #                                      inp[:,:,-2:-w_pad-2:-1,:] ], axis=2 )

    #                 h = K.concatenate ([ w[:,h_pad:0:-1,:,:],
    #                                      w,
    #                                      w[:,-2:-h_pad-2:-1,:,:] ], axis=1 )

    #                 return h
    #             else:
    #                 raise NotImplemented
    #         else:
    #             raise NotImplemented
    #f = ReflectionPadding2D.function(t, [1,65,65,1], [1,1,1,1], [1,1,1,1])

    #x, = K.function ([t],[f]) ([ image ])

    #image = np.random.uniform ( size=(1,256,256,3) )
    #image2 = np.random.uniform ( size=(1,256,256,3) )

    #t1 = K.placeholder ( (None,) + image_shape[1:], name="t1" )
    #t2 = K.placeholder ( (None,None,None,None), name="t2" )

    #l1_t = DSSIMObjective() (t1,t2 )
    #l1, = K.function([t1, t2],[l1_t]) ([image, image2])
    #
    #print (l1)
    #t[:,0:64,64::2,:].source.op.code
    """
t1[:,0:64,64::2,128:]

function (I[N0, N1, N2, N3]) -> (O)
 {\n
     Start0 = max(0, 0);
     Offset0 = Start0;
 O[
     i0, i1, i2, i3:
     ((N0 - (Start0)) + 1 - 1)/1,
     (64 + 1 - 1)/1,
     (192 + 2 - 1)/2,
     (-125 + 1 - 1)/1]
     =
     =(I[1*i0+Offset0, 1*i1+0, 2*i2+64, 1*i3+128]);

                    }

    """
    import code
    code.interact(local=dict(globals(), **locals()))






    '''
    >>> t[:,0:64,64::2,:].source.op.code
function (I[N0, N1, N2, N3]) -> (O) {

O[i0, i1, i2, i3: (1 + 1 - 1)/1, (64 + 1 - 1)/1, (64 + 2 - 1)/2, (1 + 1 - 1)/1] =
       =(I[1*i0+0, 1*i1+0, 2*i2+64, 1*i3+0]);


        Status GetWindowedOutputSizeVerboseV2(int64 input_size, int64 filter_size,
                                          int64 dilation_rate, int64 stride,
                                          Padding padding_type, int64* output_size,
                                          int64* padding_before,
                                          int64* padding_after) {
      if (stride <= 0) {
        return errors::InvalidArgument("Stride must be > 0, but got ", stride);
      }
      if (dilation_rate < 1) {
        return errors::InvalidArgument("Dilation rate must be >= 1, but got ",
                                       dilation_rate);
      }

      // See also the parallel implementation in GetWindowedOutputSizeFromDimsV2.
      int64 effective_filter_size = (filter_size - 1) * dilation_rate + 1;
      switch (padding_type) {
        case Padding::VALID:
          *output_size = (input_size - effective_filter_size + stride) / stride;
          *padding_before = *padding_after = 0;
          break;
        case Padding::EXPLICIT:
          *output_size = (input_size + *padding_before + *padding_after -
                          effective_filter_size + stride) /
                         stride;
          break;
        case Padding::SAME:
          *output_size = (input_size + stride - 1) / stride;
          const int64 padding_needed =
              std::max(int64{0}, (*output_size - 1) * stride +
                                     effective_filter_size - input_size);
          // For odd values of total padding, add more padding at the 'right'
          // side of the given dimension.
          *padding_before = padding_needed / 2;
          *padding_after = padding_needed - *padding_before;
          break;
      }
      if (*output_size < 0) {
        return errors::InvalidArgument(
            "Computed output size would be negative: ", *output_size,
            " [input_size: ", input_size,
            ", effective_filter_size: ", effective_filter_size,
            ", stride: ", stride, "]");
      }
      return Status::OK();
    }
    '''
    class ExtractImagePatchesOP(PMLTile.Operation):
        def __init__(self, input, ksizes, strides, rates, padding='valid'):

            batch, in_rows, in_cols, depth = input.shape.dims

            ksize_rows = ksizes[1];
            ksize_cols = ksizes[2];

            stride_rows = strides[1];
            stride_cols = strides[2];

            rate_rows = rates[1];
            rate_cols = rates[2];

            ksize_rows_eff = ksize_rows + (ksize_rows - 1) * (rate_rows - 1);
            ksize_cols_eff = ksize_cols + (ksize_cols - 1) * (rate_cols - 1);

            #if padding == 'valid':

            out_rows = (in_rows - ksize_rows_eff + stride_rows) / stride_rows;
            out_cols = (in_cols - ksize_cols_eff + stride_cols) / stride_cols;

            out_sizes = (batch, out_rows, out_cols, ksize_rows * ksize_cols * depth);



            B, H, W, CI = input.shape.dims

            RATE = PMLK.constant ([1,rate,rate,1], dtype=PMLK.floatx() )

            #print (target_dims)
            code = """function (I[B, {H}, {W}, {CI} ], RATES[RB, RH, RW, RC] ) -> (O) {

                        O[b, {wnd_size}, {wnd_size}, ] = =(I[b, h, w, ci]);

                    }""".format(H=H, W=W, CI=CI, RATES=rates, wnd_size=wnd_size)

            super(ExtractImagePatchesOP, self).__init__(code, [('I', input) ],
                    [('O', PMLTile.Shape(input.shape.dtype, out_sizes ) )])




    f = ExtractImagePatchesOP.function(t, [1,65,65,1], [1,1,1,1], [1,1,1,1])

    x, = K.function ([t],[f]) ([ image ])
    print(x.shape)

    import code
    code.interact(local=dict(globals(), **locals()))

    #from core.leras import nn
    #exec( nn.import_all( device_config=nn.device.Config(cpu_only=True) ), locals(), globals() )
    #
    #rnd_data = np.random.uniform( size=(1,64,64,3) )
    #bgr_shape = (64, 64, 3)
    #input_layer = Input(bgr_shape)
    #x = input_layer
    #x = Conv2D(64, 3, padding='same')(x)
    #x = Conv2D(128, 3, padding='same')(x)
    #x = Conv2D(256, 3, padding='same')(x)
    #x = Conv2D(512, 3, padding='same')(x)
    #x = Conv2D(1024, 3, padding='same')(x)
    #x = Conv2D(3, 3, padding='same')(x)
    #
    #model = Model (input_layer, [x])
    #model.compile(optimizer=Adam(), loss='mse')
    #model.train_on_batch ([rnd_data], [rnd_data])
    ##model.save (r"D:\DevelopPython\test\test_model.h5")
    #
    #import code
    #code.interact(local=dict(globals(), **locals()))



    import ffmpeg

    path = Path('D:/deepfacelab/test')
    input_path = str(path / 'input.mp4')
    #stream = ffmpeg.input(str(path / 'input.mp4') )
    #stream = ffmpeg.hflip(stream)
    #stream = ffmpeg.output(stream, str(path / 'output.mp4') )
    #ffmpeg.run(stream)
    (
        ffmpeg
        .input( str(path / 'input.mp4'))
        .hflip()
        .output( str(path / 'output.mp4'), r="23000/1001" )
        .run()
    )

    #probe = ffmpeg.probe(str(path / 'input.mp4'))

    #out, _ = (
    #    ffmpeg
    #    .input( input_path )
    #    .output('pipe:', format='rawvideo', pix_fmt='rgb24')
    #    .run(capture_stdout=True)
    #)
    #video = (
    #    np
    #    .frombuffer(out, np.uint8)
    #    .reshape([-1, height, width, 3])
    #)

    import code
    code.interact(local=dict(globals(), **locals()))




    from core.leras import nn
    exec( nn.import_all(), locals(), globals() )

    #ch = 3
    #def softmax(x, axis=-1): #from K numpy backend
    #    y = np.exp(x - np.max(x, axis, keepdims=True))
    #    return y / np.sum(y, axis, keepdims=True)
    #
    #def gauss_kernel(size, sigma):
    #    coords = np.arange(0,size, dtype=K.floatx() )
    #    coords -= (size - 1 ) / 2.0
    #    g = coords**2
    #    g *= ( -0.5 / (sigma**2) )
    #    g = np.reshape (g, (1,-1)) + np.reshape(g, (-1,1) )
    #    g = np.reshape (g, (1,-1))
    #    g = softmax(g)
    #    g = np.reshape (g, (size, size, 1, 1))
    #    g = np.tile (g, (1,1,ch, size*size*ch))
    #    return K.constant(g, dtype=K.floatx() )
    #
    ##kernel = gauss_kernel(11,1.5)
    #kernel = K.constant( np.ones ( (246,246, 3, 1) ) , dtype=K.floatx() )
    ##g = np.eye(9).reshape((3, 3, 1, 9))
    ##g = np.tile (g, (1,1,3,1))
    ##kernel = K.constant(g , dtype=K.floatx() )
    #
    #def reducer(x):
    #    shape = K.shape(x)
    #    x = K.reshape(x, (-1, shape[-3] , shape[-2], shape[-1]) )
    #
    #    y = K.depthwise_conv2d(x, kernel, strides=(1, 1), padding='valid')
    #
    #    y_shape = K.shape(y)
    #    return y#K.reshape(y, (shape[0], y_shape[1], y_shape[2], y_shape[3] ) )

    image = cv2.imread('D:\\DeepFaceLab\\test\\00000.png').astype(np.float32) / 255.0
    image = cv2.resize ( image, (128,128) )

    image = cv2.cvtColor (image, cv2.COLOR_BGR2GRAY)
    image = np.expand_dims (image, -1)
    image_shape = image.shape

    image2 = cv2.imread('D:\\DeepFaceLab\\test\\00001.png').astype(np.float32) / 255.0
    #image2 = cv2.cvtColor (image2, cv2.COLOR_BGR2GRAY)
    #image2 = np.expand_dims (image2, -1)
    image2_shape = image2.shape

    image_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )
    image2_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )

    #loss = reducer(image_tensor)
    #loss = K.reshape (loss, (-1,246,246, 11,11,3) )
    tf = nn.tf

    sh = K.int_shape(image_tensor)[1]
    wnd_size = 16
    step_size = 8
    k = (sh-wnd_size) // step_size + 1

    loss = tf.image.extract_image_patches(image_tensor, [1,k,k,1], [1,1,1,1], [1,step_size,step_size,1], 'VALID')
    print(loss)

    f = K.function ( [image_tensor], [loss] )
    x = f ( [ np.expand_dims(image,0) ] )[0][0]

    import code
    code.interact(local=dict(globals(), **locals()))

    for i in range( x.shape[2] ):
        img = x[:,:,i:i+1]

        cv2.imshow('', (img*255).astype(np.uint8) )
        cv2.waitKey(0)

    #for i in range( len(x) ):
    #    for j in range ( len(x) ):
    #        img = x[i,j]
    #        import code
    #        code.interact(local=dict(globals(), **locals()))
    #
    #        cv2.imshow('', (x[i,j]*255).astype(np.uint8) )
    #        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    from core.leras import nn
    exec( nn.import_all(), locals(), globals() )

    PNet_Input = Input ( (None, None,3) )
    x = PNet_Input
    x = Conv2D (10, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU1" )(x)
    x = MaxPooling2D( pool_size=(2,2), strides=(2,2), padding='same' ) (x)
    x = Conv2D (16, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU2" )(x)
    x = Conv2D (32, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU3" )(x)
    prob = Conv2D (2, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv41")(x)
    prob = Softmax()(prob)
    x = Conv2D (4, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv42")(x)

    PNet_model = Model(PNet_Input, [x,prob] )
    PNet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_pnet.h5').__str__() )

    RNet_Input = Input ( (24, 24, 3) )
    x = RNet_Input
    x = Conv2D (28, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="prelu1" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='same' ) (x)
    x = Conv2D (48, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="prelu2" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='valid' ) (x)
    x = Conv2D (64, kernel_size=(2,2), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="prelu3" )(x)
    x = Lambda ( lambda x: K.reshape (x, (-1, np.prod(K.int_shape(x)[1:]),) ), output_shape=(np.prod(K.int_shape(x)[1:]),) ) (x)
    x = Dense (128, name='conv4')(x)
    x = PReLU (name="prelu4" )(x)
    prob = Dense (2, name='conv51')(x)
    prob = Softmax()(prob)
    x = Dense (4, name='conv52')(x)
    RNet_model = Model(RNet_Input, [x,prob] )
    RNet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_rnet.h5').__str__() )

    ONet_Input = Input ( (48, 48, 3) )
    x = ONet_Input
    x = Conv2D (32, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="prelu1" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='same' ) (x)
    x = Conv2D (64, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="prelu2" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='valid' ) (x)
    x = Conv2D (64, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="prelu3" )(x)
    x = MaxPooling2D( pool_size=(2,2), strides=(2,2), padding='same' ) (x)
    x = Conv2D (128, kernel_size=(2,2), strides=(1,1), padding='valid', name="conv4")(x)
    x = PReLU (shared_axes=[1,2], name="prelu4" )(x)
    x = Lambda ( lambda x: K.reshape (x, (-1, np.prod(K.int_shape(x)[1:]),) ), output_shape=(np.prod(K.int_shape(x)[1:]),) ) (x)
    x = Dense (256, name='conv5')(x)
    x = PReLU (name="prelu5" )(x)
    prob = Dense (2, name='conv61')(x)
    prob = Softmax()(prob)
    x1 = Dense (4, name='conv62')(x)
    x2 = Dense (10, name='conv63')(x)
    ONet_model = Model(ONet_Input, [x1,x2,prob] )
    ONet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_onet.h5').__str__() )

    pnet_fun = K.function ( PNet_model.inputs, PNet_model.outputs )
    rnet_fun = K.function ( RNet_model.inputs, RNet_model.outputs )
    onet_fun = K.function ( ONet_model.inputs, ONet_model.outputs )

    pnet_test_data = np.random.uniform ( size=(1, 64,64,3) )
    pnet_result1, pnet_result2 = pnet_fun ([pnet_test_data])

    rnet_test_data = np.random.uniform ( size=(1,24,24,3) )
    rnet_result1, rnet_result2 = rnet_fun ([rnet_test_data])

    onet_test_data = np.random.uniform ( size=(1,48,48,3) )
    onet_result1, onet_result2, onet_result3 = onet_fun ([onet_test_data])

    import code
    code.interact(local=dict(globals(), **locals()))

    from core.leras import nn
    #exec( nn.import_all( nn.device.Config(cpu_only=True) ), locals(), globals() )# nn.device.Config(cpu_only=True)
    exec( nn.import_all(), locals(), globals() )# nn.device.Config(cpu_only=True)

    #det1_Input = Input ( (None, None,3) )
    #x = det1_Input
    #x = Conv2D (10, kernel_size=(3,3), strides=(1,1), padding='valid')(x)
    #
    #import code
    #code.interact(local=dict(globals(), **locals()))

    tf = nn.tf
    tf_session = nn.tf_sess

    with tf.variable_scope('pnet2'):
        data = tf.placeholder(tf.float32, (None,None,None,3), 'input')
        pnet2 = mtcnn.PNet(tf, {'data':data})
        pnet2.load( (Path(mtcnn.__file__).parent / 'det1.npy').__str__(), tf_session)
    with tf.variable_scope('rnet2'):
        data = tf.placeholder(tf.float32, (None,24,24,3), 'input')
        rnet2 = mtcnn.RNet(tf, {'data':data})
        rnet2.load( (Path(mtcnn.__file__).parent / 'det2.npy').__str__(), tf_session)
    with tf.variable_scope('onet2'):
        data = tf.placeholder(tf.float32, (None,48,48,3), 'input')
        onet2 = mtcnn.ONet(tf, {'data':data})
        onet2.load( (Path(mtcnn.__file__).parent / 'det3.npy').__str__(), tf_session)



    pnet_fun = K.function([pnet2.layers['data']],[pnet2.layers['conv4-2'], pnet2.layers['prob1']])
    rnet_fun = K.function([rnet2.layers['data']],[rnet2.layers['conv5-2'], rnet2.layers['prob1']])
    onet_fun = K.function([onet2.layers['data']],[onet2.layers['conv6-2'], onet2.layers['conv6-3'], onet2.layers['prob1']])

    det1_dict = np.load((Path(mtcnn.__file__).parent / 'det1.npy').__str__(), encoding='latin1').item()
    det2_dict = np.load((Path(mtcnn.__file__).parent / 'det2.npy').__str__(), encoding='latin1').item()
    det3_dict = np.load((Path(mtcnn.__file__).parent / 'det3.npy').__str__(), encoding='latin1').item()

    PNet_Input = Input ( (None, None,3) )
    x = PNet_Input
    x = Conv2D (10, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU1" )(x)
    x = MaxPooling2D( pool_size=(2,2), strides=(2,2), padding='same' ) (x)
    x = Conv2D (16, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU2" )(x)
    x = Conv2D (32, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="PReLU3" )(x)
    prob = Conv2D (2, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv41")(x)
    prob = Softmax()(prob)
    x = Conv2D (4, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv42")(x)


    PNet_model = Model(PNet_Input, [x,prob] )

    #PNet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_pnet.h5').__str__() )
    PNet_model.get_layer("conv1").set_weights ( [ det1_dict['conv1']['weights'], det1_dict['conv1']['biases'] ] )
    PNet_model.get_layer("PReLU1").set_weights ( [ np.reshape(det1_dict['PReLU1']['alpha'], (1,1,-1)) ] )
    PNet_model.get_layer("conv2").set_weights ( [ det1_dict['conv2']['weights'], det1_dict['conv2']['biases'] ] )
    PNet_model.get_layer("PReLU2").set_weights ( [ np.reshape(det1_dict['PReLU2']['alpha'], (1,1,-1)) ] )
    PNet_model.get_layer("conv3").set_weights ( [ det1_dict['conv3']['weights'], det1_dict['conv3']['biases'] ] )
    PNet_model.get_layer("PReLU3").set_weights ( [ np.reshape(det1_dict['PReLU3']['alpha'], (1,1,-1)) ] )
    PNet_model.get_layer("conv41").set_weights ( [ det1_dict['conv4-1']['weights'], det1_dict['conv4-1']['biases'] ] )
    PNet_model.get_layer("conv42").set_weights ( [ det1_dict['conv4-2']['weights'], det1_dict['conv4-2']['biases'] ] )
    PNet_model.save ( (Path(mtcnn.__file__).parent / 'mtcnn_pnet.h5').__str__() )

    pnet_test_data = np.random.uniform ( size=(1, 64,64,3) )
    pnet_result1, pnet_result2 = pnet_fun ([pnet_test_data])
    pnet2_result1, pnet2_result2 =  K.function ( PNet_model.inputs, PNet_model.outputs ) ([pnet_test_data])

    pnet_diff1 = np.mean ( np.abs(pnet_result1 - pnet2_result1) )
    pnet_diff2 = np.mean ( np.abs(pnet_result2 - pnet2_result2) )
    print ("pnet_diff1 = %f, pnet_diff2 = %f, "  % (pnet_diff1, pnet_diff2) )

    RNet_Input = Input ( (24, 24, 3) )
    x = RNet_Input
    x = Conv2D (28, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="prelu1" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='same' ) (x)
    x = Conv2D (48, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="prelu2" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='valid' ) (x)
    x = Conv2D (64, kernel_size=(2,2), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="prelu3" )(x)
    x = Lambda ( lambda x: K.reshape (x, (-1, np.prod(K.int_shape(x)[1:]),) ), output_shape=(np.prod(K.int_shape(x)[1:]),) ) (x)
    x = Dense (128, name='conv4')(x)
    x = PReLU (name="prelu4" )(x)
    prob = Dense (2, name='conv51')(x)
    prob = Softmax()(prob)
    x = Dense (4, name='conv52')(x)

    RNet_model = Model(RNet_Input, [x,prob] )

    #RNet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_rnet.h5').__str__() )
    RNet_model.get_layer("conv1").set_weights ( [ det2_dict['conv1']['weights'], det2_dict['conv1']['biases'] ] )
    RNet_model.get_layer("prelu1").set_weights ( [ np.reshape(det2_dict['prelu1']['alpha'], (1,1,-1)) ] )
    RNet_model.get_layer("conv2").set_weights ( [ det2_dict['conv2']['weights'], det2_dict['conv2']['biases'] ] )
    RNet_model.get_layer("prelu2").set_weights ( [ np.reshape(det2_dict['prelu2']['alpha'], (1,1,-1)) ] )
    RNet_model.get_layer("conv3").set_weights ( [ det2_dict['conv3']['weights'], det2_dict['conv3']['biases'] ] )
    RNet_model.get_layer("prelu3").set_weights ( [ np.reshape(det2_dict['prelu3']['alpha'], (1,1,-1)) ] )
    RNet_model.get_layer("conv4").set_weights ( [ det2_dict['conv4']['weights'], det2_dict['conv4']['biases'] ] )
    RNet_model.get_layer("prelu4").set_weights ( [ det2_dict['prelu4']['alpha'] ] )
    RNet_model.get_layer("conv51").set_weights ( [ det2_dict['conv5-1']['weights'], det2_dict['conv5-1']['biases'] ] )
    RNet_model.get_layer("conv52").set_weights ( [ det2_dict['conv5-2']['weights'], det2_dict['conv5-2']['biases'] ] )
    RNet_model.save ( (Path(mtcnn.__file__).parent / 'mtcnn_rnet.h5').__str__() )

    #import code
    #code.interact(local=dict(globals(), **locals()))

    rnet_test_data = np.random.uniform ( size=(1,24,24,3) )
    rnet_result1, rnet_result2 = rnet_fun ([rnet_test_data])
    rnet2_result1, rnet2_result2 =  K.function ( RNet_model.inputs, RNet_model.outputs ) ([rnet_test_data])

    rnet_diff1 = np.mean ( np.abs(rnet_result1 - rnet2_result1) )
    rnet_diff2 = np.mean ( np.abs(rnet_result2 - rnet2_result2) )
    print ("rnet_diff1 = %f, rnet_diff2 = %f, "  % (rnet_diff1, rnet_diff2) )


    #################
    '''
    (self.feed('data') #pylint: disable=no-value-for-parameter, no-member
             .conv(3, 3, 32, 1, 1, padding='VALID', relu=False, name='conv1')
             .prelu(name='prelu1')
             .max_pool(3, 3, 2, 2, name='pool1')
             .conv(3, 3, 64, 1, 1, padding='VALID', relu=False, name='conv2')
             .prelu(name='prelu2')
             .max_pool(3, 3, 2, 2, padding='VALID', name='pool2')
             .conv(3, 3, 64, 1, 1, padding='VALID', relu=False, name='conv3')
             .prelu(name='prelu3')
             .max_pool(2, 2, 2, 2, name='pool3')
             .conv(2, 2, 128, 1, 1, padding='VALID', relu=False, name='conv4')
             .prelu(name='prelu4')
             .fc(256, relu=False, name='conv5')
             .prelu(name='prelu5')
             .fc(2, relu=False, name='conv6-1')
             .softmax(1, name='prob1'))

        (self.feed('prelu5') #pylint: disable=no-value-for-parameter
             .fc(4, relu=False, name='conv6-2'))

        (self.feed('prelu5') #pylint: disable=no-value-for-parameter
             .fc(10, relu=False, name='conv6-3'))
    '''
    ONet_Input = Input ( (48, 48, 3) )
    x = ONet_Input
    x = Conv2D (32, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    x = PReLU (shared_axes=[1,2], name="prelu1" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='same' ) (x)
    x = Conv2D (64, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    x = PReLU (shared_axes=[1,2], name="prelu2" )(x)
    x = MaxPooling2D( pool_size=(3,3), strides=(2,2), padding='valid' ) (x)
    x = Conv2D (64, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv3")(x)
    x = PReLU (shared_axes=[1,2], name="prelu3" )(x)
    x = MaxPooling2D( pool_size=(2,2), strides=(2,2), padding='same' ) (x)
    x = Conv2D (128, kernel_size=(2,2), strides=(1,1), padding='valid', name="conv4")(x)
    x = PReLU (shared_axes=[1,2], name="prelu4" )(x)
    x = Lambda ( lambda x: K.reshape (x, (-1, np.prod(K.int_shape(x)[1:]),) ), output_shape=(np.prod(K.int_shape(x)[1:]),) ) (x)
    x = Dense (256, name='conv5')(x)
    x = PReLU (name="prelu5" )(x)
    prob = Dense (2, name='conv61')(x)
    prob = Softmax()(prob)
    x1 = Dense (4, name='conv62')(x)
    x2 = Dense (10, name='conv63')(x)

    ONet_model = Model(ONet_Input, [x1,x2,prob] )

    #ONet_model.load_weights ( (Path(mtcnn.__file__).parent / 'mtcnn_onet.h5').__str__() )
    ONet_model.get_layer("conv1").set_weights ( [ det3_dict['conv1']['weights'], det3_dict['conv1']['biases'] ] )
    ONet_model.get_layer("prelu1").set_weights ( [ np.reshape(det3_dict['prelu1']['alpha'], (1,1,-1)) ] )
    ONet_model.get_layer("conv2").set_weights ( [ det3_dict['conv2']['weights'], det3_dict['conv2']['biases'] ] )
    ONet_model.get_layer("prelu2").set_weights ( [ np.reshape(det3_dict['prelu2']['alpha'], (1,1,-1)) ] )
    ONet_model.get_layer("conv3").set_weights ( [ det3_dict['conv3']['weights'], det3_dict['conv3']['biases'] ] )
    ONet_model.get_layer("prelu3").set_weights ( [ np.reshape(det3_dict['prelu3']['alpha'], (1,1,-1)) ] )
    ONet_model.get_layer("conv4").set_weights ( [ det3_dict['conv4']['weights'], det3_dict['conv4']['biases'] ] )
    ONet_model.get_layer("prelu4").set_weights ( [ np.reshape(det3_dict['prelu4']['alpha'], (1,1,-1)) ] )
    ONet_model.get_layer("conv5").set_weights ( [ det3_dict['conv5']['weights'], det3_dict['conv5']['biases'] ] )
    ONet_model.get_layer("prelu5").set_weights ( [ det3_dict['prelu5']['alpha'] ] )
    ONet_model.get_layer("conv61").set_weights ( [ det3_dict['conv6-1']['weights'], det3_dict['conv6-1']['biases'] ] )
    ONet_model.get_layer("conv62").set_weights ( [ det3_dict['conv6-2']['weights'], det3_dict['conv6-2']['biases'] ] )
    ONet_model.get_layer("conv63").set_weights ( [ det3_dict['conv6-3']['weights'], det3_dict['conv6-3']['biases'] ] )
    ONet_model.save ( (Path(mtcnn.__file__).parent / 'mtcnn_onet.h5').__str__() )

    onet_test_data = np.random.uniform ( size=(1,48,48,3) )
    onet_result1, onet_result2, onet_result3 = onet_fun ([onet_test_data])
    onet2_result1, onet2_result2, onet2_result3 =  K.function ( ONet_model.inputs, ONet_model.outputs ) ([onet_test_data])

    onet_diff1 = np.mean ( np.abs(onet_result1 - onet2_result1) )
    onet_diff2 = np.mean ( np.abs(onet_result2 - onet2_result2) )
    onet_diff3 = np.mean ( np.abs(onet_result3 - onet2_result3) )
    print ("onet_diff1 = %f, onet_diff2 = %f, , onet_diff3 = %f "  % (onet_diff1, onet_diff2, onet_diff3) )


    import code
    code.interact(local=dict(globals(), **locals()))





    import code
    code.interact(local=dict(globals(), **locals()))






    #class MTCNNSoftmax(keras.Layer):
    #
    #    def __init__(self, axis=-1, **kwargs):
    #        super(MTCNNSoftmax, self).__init__(**kwargs)
    #        self.supports_masking = True
    #        self.axis = axis
    #
    #    def call(self, inputs):
    #
    #    def softmax(self, target, axis, name=None):
    #        max_axis = self.tf.reduce_max(target, axis, keepdims=True)
    #        target_exp = self.tf.exp(target-max_axis)
    #        normalize = self.tf.reduce_sum(target_exp, axis, keepdims=True)
    #        softmax = self.tf.div(target_exp, normalize, name)
    #        return softmax
    #        #return activations.softmax(inputs, axis=self.axis)
    #
    #    def get_config(self):
    #        config = {'axis': self.axis}
    #        base_config = super(MTCNNSoftmax, self).get_config()
    #        return dict(list(base_config.items()) + list(config.items()))
    #
    #    def compute_output_shape(self, input_shape):
    #        return input_shape

    from core.leras import nn
    exec( nn.import_all(), locals(), globals() )




    image = cv2.imread('D:\\DeepFaceLab\\test\\00000.png').astype(np.float32) / 255.0
    image = cv2.cvtColor (image, cv2.COLOR_BGR2GRAY)
    image = np.expand_dims (image, -1)
    image_shape = image.shape

    image2 = cv2.imread('D:\\DeepFaceLab\\test\\00001.png').astype(np.float32) / 255.0
    image2 = cv2.cvtColor (image2, cv2.COLOR_BGR2GRAY)
    image2 = np.expand_dims (image2, -1)
    image2_shape = image2.shape

    #cv2.imshow('', image)


    image_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )
    image2_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )

    blurred_image_tensor = gaussian_blur(16.0)(image_tensor)
    x, = nn.tf_sess.run ( blurred_image_tensor, feed_dict={image_tensor: np.expand_dims(image,0)} )
    cv2.imshow('', (x*255).astype(np.uint8) )
    cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))


    #os.environ['plaidML'] = '1'
    from core.leras import nn

    dvc = nn.device.Config(force_gpu_idx=1)
    exec( nn.import_all(dvc), locals(), globals() )

    tf = nn.tf

    image = cv2.imread('D:\\DeepFaceLab\\test\\00000.png').astype(np.float32) / 255.0
    image = cv2.cvtColor (image, cv2.COLOR_BGR2GRAY)
    image = np.expand_dims (image, -1)
    image_shape = image.shape

    image2 = cv2.imread('D:\\DeepFaceLab\\test\\00001.png').astype(np.float32) / 255.0
    image2 = cv2.cvtColor (image2, cv2.COLOR_BGR2GRAY)
    image2 = np.expand_dims (image2, -1)
    image2_shape = image2.shape

    image1_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )
    image2_tensor = K.placeholder(shape=[ 1, image_shape[0], image_shape[1], image_shape[2] ], dtype="float32" )



    #import code
    #code.interact(local=dict(globals(), **locals()))
    def manual_conv(input, filter, strides, padding):
          h_f, w_f, c_in, c_out = filter.get_shape().as_list()
          input_patches = tf.extract_image_patches(input, ksizes=[1, h_f, w_f, 1 ], strides=strides, rates=[1, 1, 1, 1], padding=padding)
          return input_patches
          filters_flat = tf.reshape(filter, shape=[h_f*w_f*c_in, c_out])
          return tf.einsum("ijkl,lm->ijkm", input_patches, filters_flat)

    def extract_image_patches(x, ksizes, ssizes, padding='SAME',
                          data_format='channels_last'):
        """Extract the patches from an image.
        # Arguments
            x: The input image
            ksizes: 2-d tuple with the kernel size
            ssizes: 2-d tuple with the strides size
            padding: 'same' or 'valid'
            data_format: 'channels_last' or 'channels_first'
        # Returns
            The (k_w,k_h) patches extracted
            TF ==> (batch_size,w,h,k_w,k_h,c)
            TH ==> (batch_size,w,h,c,k_w,k_h)
        """
        kernel = [1, ksizes[0], ksizes[1], 1]
        strides = [1, ssizes[0], ssizes[1], 1]
        if data_format == 'channels_first':
            x = K.permute_dimensions(x, (0, 2, 3, 1))
        bs_i, w_i, h_i, ch_i = K.int_shape(x)
        patches = tf.extract_image_patches(x, kernel, strides, [1, 1, 1, 1],
                                           padding)
        # Reshaping to fit Theano
        bs, w, h, ch = K.int_shape(patches)
        reshaped = tf.reshape(patches, [-1, w, h, tf.floordiv(ch, ch_i), ch_i])
        final_shape = [-1, w, h, ch_i, ksizes[0], ksizes[1]]
        patches = tf.reshape(tf.transpose(reshaped, [0, 1, 2, 4, 3]), final_shape)
        if data_format == 'channels_last':
            patches = K.permute_dimensions(patches, [0, 1, 2, 4, 5, 3])
        return patches

    m = 32
    c_in = 3
    c_out = 16

    filter_sizes = [5, 11]
    strides = [1]
    #paddings = ["VALID", "SAME"]

    for fs in filter_sizes:
        h = w = 128
        h_f = w_f = fs
        stri = 2
        #print "Testing for", imsize, fs, stri, pad

        #tf.reset_default_graph()
        X = tf.constant(1.0+np.random.rand(m, h, w, c_in), tf.float32)
        W = tf.constant(np.ones([h_f, w_f, c_in, h_f*w_f*c_in]), tf.float32)


        Z = tf.nn.conv2d(X, W, strides=[1, stri, stri, 1], padding="VALID")
        Z_manual = manual_conv(X, W, strides=[1, stri, stri, 1], padding="VALID")
        Z_2 = extract_image_patches (X, (fs,fs), (stri,stri),  padding="VALID")
        import code
        code.interact(local=dict(globals(), **locals()))
        #
        sess = tf.Session()
        sess.run(tf.global_variables_initializer())
        Z_, Z_manual_ = sess.run([Z, Z_manual])
        #self.assertEqual(Z_.shape, Z_manual_.shape)
        #self.assertTrue(np.allclose(Z_, Z_manual_, rtol=1e-05))
        sess.close()


        import code
        code.interact(local=dict(globals(), **locals()))





    #k_loss_t = keras_style_loss()(image1_tensor, image2_tensor)
    #k_loss_run = K.function( [image1_tensor, image2_tensor],[k_loss_t])
    #import code
    #code.interact(local=dict(globals(), **locals()))
    #image = np.expand_dims(image,0)
    #image2 = np.expand_dims(image2,0)
    #k_loss = k_loss_run([image, image2])
    #t_loss = t_loss_run([image, image2])




    #x, = tf_sess_run ([np.expand_dims(image,0)])
    #x = x[0]
    ##import code
    ##code.interact(local=dict(globals(), **locals()))



    image = cv2.imread('D:\\DeepFaceLab\\test\\00000.png').astype(np.float32) / 255.0
    image = cv2.cvtColor (image, cv2.COLOR_BGR2GRAY)
    image = np.expand_dims (image, -1)
    image_shape = image.shape

    image2 = cv2.imread('D:\\DeepFaceLab\\test\\00001.png').astype(np.float32) / 255.0
    image2 = cv2.cvtColor (image2, cv2.COLOR_BGR2GRAY)
    image2 = np.expand_dims (image2, -1)
    image2_shape = image2.shape

    image_tensor = tf.placeholder(tf.float32, shape=[1, image_shape[0], image_shape[1], image_shape[2] ])
    image2_tensor = tf.placeholder(tf.float32, shape=[1, image2_shape[0], image2_shape[1], image2_shape[2] ])

    blurred_image_tensor = sl(image_tensor, image2_tensor)
    x = tf_sess.run ( blurred_image_tensor, feed_dict={image_tensor: np.expand_dims(image,0), image2_tensor: np.expand_dims(image2,0) } )

    cv2.imshow('', x[0])
    cv2.waitKey(0)
    import code
    code.interact(local=dict(globals(), **locals()))

    while True:
        image = cv2.imread('D:\\DeepFaceLab\\workspace\\data_src\\aligned\\00000.png').astype(np.float32) / 255.0
        image = cv2.resize(image, (256,256))
        image = random_transform( image )
        warped_img, target_img = random_warp( image )

        #cv2.imshow('', image)
        #cv2.waitKey(0)

        cv2.imshow('', warped_img)
        cv2.waitKey(0)
        cv2.imshow('', target_img)
        cv2.waitKey(0)

    import code
    code.interact(local=dict(globals(), **locals()))

    import code
    code.interact(local=dict(globals(), **locals()))

    return


    def keras_gaussian_blur(radius=2.0):
        def gaussian(x, mu, sigma):
            return np.exp(-(float(x) - float(mu)) ** 2 / (2 * sigma ** 2))

        def make_kernel(sigma):
            kernel_size = max(3, int(2 * 2 * sigma + 1))
            mean = np.floor(0.5 * kernel_size)
            kernel_1d = np.array([gaussian(x, mean, sigma) for x in range(kernel_size)])
            np_kernel = np.outer(kernel_1d, kernel_1d).astype(dtype=K.floatx())
            kernel = np_kernel / np.sum(np_kernel)
            return kernel

        gauss_kernel = make_kernel(radius)
        gauss_kernel = gauss_kernel[:, :,np.newaxis, np.newaxis]

        #import code
        #code.interact(local=dict(globals(), **locals()))
        def func(input):
            inputs = [ input[:,:,:,i:i+1]  for i in range( K.int_shape( input )[-1] ) ]

            outputs = []
            for i in range(len(inputs)):
                outputs += [ K.conv2d( inputs[i] , K.constant(gauss_kernel) , strides=(1,1), padding="same") ]

            return K.concatenate (outputs, axis=-1)
        return func

    def keras_style_loss(gaussian_blur_radius=0.0, loss_weight=1.0, epsilon=1e-5):
        if gaussian_blur_radius > 0.0:
            gblur = keras_gaussian_blur(gaussian_blur_radius)

        def sd(content, style):
            content_nc = K.int_shape(content)[-1]
            style_nc = K.int_shape(style)[-1]
            if content_nc != style_nc:
                raise Exception("keras_style_loss() content_nc != style_nc")

            axes = [1,2]
            c_mean, c_var = K.mean(content, axis=axes, keepdims=True), K.var(content, axis=axes, keepdims=True)
            s_mean, s_var = K.mean(style, axis=axes, keepdims=True), K.var(style, axis=axes, keepdims=True)
            c_std, s_std = K.sqrt(c_var + epsilon), K.sqrt(s_var + epsilon)

            mean_loss = K.sum(K.square(c_mean-s_mean))
            std_loss = K.sum(K.square(c_std-s_std))

            return (mean_loss + std_loss) * loss_weight

        def func(target, style):
            if gaussian_blur_radius > 0.0:
                return sd( gblur(target), gblur(style))
            else:
                return sd( target, style )
        return func

    data = tf.placeholder(tf.float32, (None,None,None,3), 'input')
    pnet2 = mtcnn.PNet(tf, {'data':data})
    filename = str(Path(mtcnn.__file__).parent/'det1.npy')
    pnet2.load(filename, tf_sess)

    pnet_fun = K.function([pnet2.layers['data']],[pnet2.layers['conv4-2'], pnet2.layers['prob1']])

    import code
    code.interact(local=dict(globals(), **locals()))

    return


    while True:
        img_bgr = np.random.rand ( 268, 640, 3 )
        img_size = img_bgr.shape[1], img_bgr.shape[0]

        mat = np.array( [[ 1.99319629e+00, -1.81504324e-01, -3.62479778e+02],
                         [ 1.81504324e-01,  1.99319629e+00, -8.05396709e+01]] )

        tmp_0 = np.random.rand ( 128,128 ) - 0.1
        tmp   = np.expand_dims (tmp_0, axis=-1)

        mask = np.ones ( tmp.shape, dtype=np.float32)
        mask_border_size = int ( mask.shape[1] * 0.0625 )
        mask[:,0:mask_border_size,:] = 0
        mask[:,-mask_border_size:,:] = 0

        x = cv2.warpAffine( mask, mat, img_size, np.zeros(img_bgr.shape, dtype=np.float32), cv2.WARP_INVERSE_MAP | cv2.INTER_LANCZOS4, cv2.BORDER_TRANSPARENT )

        if len ( np.argwhere( np.isnan(x) ) ) == 0:
            print ("fine")
        else:
            print ("wtf")

    import code
    code.interact(local=dict(globals(), **locals()))

    return

    aligned_path_image_paths = pathex.get_image_paths("E:\\FakeFaceVideoSources\\Datasets\\CelebA aligned")

    a = []
    r_vec = np.array([[0.01891013], [0.08560084], [-3.14392813]])
    t_vec = np.array([[-14.97821226], [-10.62040383], [-2053.03596872]])

    yaws = []
    pitchs = []
    for filepath in tqdm(aligned_path_image_paths, desc="test", ascii=True ):
        filepath = Path(filepath)

        if filepath.suffix == '.png':
            dflimg = DFLPNG.load( str(filepath), print_on_no_embedded_data=True )
        elif filepath.suffix == '.jpg':
            dflimg = DFLJPG.load ( str(filepath), print_on_no_embedded_data=True )
        else:
            print ("%s is not a dfl image file" % (filepath.name) )

        #source_filename_stem = Path( dflimg.get_source_filename() ).stem
        #if source_filename_stem not in alignments.keys():
        #    alignments[ source_filename_stem ] = []


        #focal_length = dflimg.shape[1]
        #camera_center = (dflimg.shape[1] / 2, dflimg.shape[0] / 2)
        #camera_matrix = np.array(
        #    [[focal_length, 0, camera_center[0]],
        #     [0, focal_length, camera_center[1]],
        #     [0, 0, 1]], dtype=np.float32)
        #
        landmarks = dflimg.get_landmarks()
        #
        #lm = landmarks.astype(np.float32)

        img = cv2_imread (str(filepath)) / 255.0

        img = LandmarksProcessor.draw_landmarks(img, landmarks, (1,1,1) )


        #(_, rotation_vector, translation_vector) = cv2.solvePnP(
        #    LandmarksProcessor.landmarks_68_3D,
        #    lm,
        #    camera_matrix,
        #    np.zeros((4, 1)) )
        #
        #rme = mathlib.rotationMatrixToEulerAngles( cv2.Rodrigues(rotation_vector)[0] )
        #import code
        #code.interact(local=dict(globals(), **locals()))

        #rotation_vector = rotation_vector / np.linalg.norm(rotation_vector)


        #img2 = image_utils.get_text_image ( (256,10, 3), str(rotation_vector) )
        pitch, yaw = LandmarksProcessor.estimate_pitch_yaw (landmarks)
        yaws += [yaw]
        #print(pitch, yaw)
        #cv2.imshow ("", (img * 255).astype(np.uint8) )
        #cv2.waitKey(0)
        #a += [ rotation_vector]
    yaws = np.array(yaws)
    import code
    code.interact(local=dict(globals(), **locals()))






        #alignments[ source_filename_stem ].append (dflimg.get_source_landmarks())
        #alignments.append (dflimg.get_source_landmarks())







    o = np.ones ( (128,128,3), dtype=np.float32 )
    cv2.imwrite ("D:\\temp\\z.jpg", o)

    #DFLJPG.x ("D:\\temp\\z.jpg", )

    dfljpg = DFLJPG.load("D:\\temp\\z.jpg")

    import code
    code.interact(local=dict(globals(), **locals()))

    return



    import sys, numpy; print(numpy.__version__, sys.version)
    sq = multiprocessing.Queue()
    cq = multiprocessing.Queue()

    p = multiprocessing.Process(target=subprocess, args=(sq,cq,))
    p.start()

    while True:
        cq.get() #waiting numpy array
        sq.put (1) #send message we are ready to get more

    #import code
    #code.interact(local=dict(globals(), **locals()))

    os.environ['TF_MIN_GPU_MULTIPROCESSOR_COUNT'] = '2'

    from core.leras import nn
    exec( nn.import_all(), locals(), globals() )




    #import tensorflow as tf
    #tf_module = tf
    #
    #config = tf_module.ConfigProto()
    #config.gpu_options.force_gpu_compatible = True
    #tf_session = tf_module.Session(config=config)
    #
    #srgb_tensor = tf.placeholder("float", [None, None, 3])
    #
    #filename = Path(__file__).parent / '00050.png'
    #img = cv2.imread(str(filename)).astype(np.float32) / 255.0
    #
    #lab_tensor = rgb_to_lab (tf_module, srgb_tensor)
    #
    #rgb_tensor = lab_to_rgb (tf_module, lab_tensor)
    #
    #rgb = tf_session.run(rgb_tensor, feed_dict={srgb_tensor: img})
    #cv2.imshow("", rgb)
    #cv2.waitKey(0)

    #from skimage import io, color
    #def_lab = color.rgb2lab(img)
    #
    #t = time.time()
    #def_lab = color.rgb2lab(img)
    #print ( time.time() - t )
    #
    #lab = tf_session.run(lab_tensor, feed_dict={srgb_tensor: img})
    #
    #t = time.time()
    #lab = tf_session.run(lab_tensor, feed_dict={srgb_tensor: img})
    #print ( time.time() - t )






    #lab_clr = color.rgb2lab(img_bgr)
    #lab_bw = color.rgb2lab(out_img)
    #tmp_channel, a_channel, b_channel = cv2.split(lab_clr)
    #l_channel, tmp2_channel, tmp3_channel = cv2.split(lab_bw)
    #img_LAB = cv2.merge((l_channel,a_channel, b_channel))
    #out_img = color.lab2rgb(lab.astype(np.float64))
    #
    #cv2.imshow("", out_img)
    #cv2.waitKey(0)

    #import code
    #code.interact(local=dict(globals(), **locals()))



if __name__ == "__main__":

    #import os
    #os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
    #os.environ["PLAIDML_DEVICE_IDS"] = "opencl_nvidia_geforce_gtx_1060_6gb.0"
    #import keras
    #import numpy as np
    #import cv2
    #import time
    #K = keras.backend
    #
    #
    #
    #PNet_Input = keras.layers.Input ( (None, None,3) )
    #x = PNet_Input
    #x = keras.layers.Conv2D (10, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv1")(x)
    #x = keras.layers.PReLU (shared_axes=[1,2], name="PReLU1" )(x)
    #x = keras.layers.MaxPooling2D( pool_size=(2,2), strides=(2,2), padding='same' ) (x)
    #x = keras.layers.Conv2D (16, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv2")(x)
    #x = keras.layers.PReLU (shared_axes=[1,2], name="PReLU2" )(x)
    #x = keras.layers.Conv2D (32, kernel_size=(3,3), strides=(1,1), padding='valid', name="conv3")(x)
    #x = keras.layers.PReLU (shared_axes=[1,2], name="PReLU3" )(x)
    #prob = keras.layers.Conv2D (2, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv41")(x)
    #x = keras.layers.Conv2D (4, kernel_size=(1,1), strides=(1,1), padding='valid', name="conv42")(x)
    #
    #pnet = K.function ([PNet_Input], [x,prob] )
    #
    #img = np.random.uniform ( size=(1920,1920,3) )
    #minsize=80
    #factor=0.95
    #factor_count=0
    #h=img.shape[0]
    #w=img.shape[1]
    #
    #minl=np.amin([h, w])
    #m=12.0/minsize
    #minl=minl*m
    ## create scale pyramid
    #scales=[]
    #while minl>=12:
    #    scales += [m*np.power(factor, factor_count)]
    #    minl = minl*factor
    #    factor_count += 1
    #    # first stage
    #    for scale in scales:
    #        hs=int(np.ceil(h*scale))
    #        ws=int(np.ceil(w*scale))
    #        im_data = cv2.resize(img, (ws, hs), interpolation=cv2.INTER_LINEAR)
    #        im_data = (im_data-127.5)*0.0078125
    #        img_x = np.expand_dims(im_data, 0)
    #        img_x = np.transpose(img_x, (0,2,1,3))
    #        t = time.time()
    #        out = pnet([img_x])
    #        t = time.time() - t
    #        print (img_x.shape, t)
    #
    #import code
    #code.interact(local=dict(globals(), **locals()))

    #os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
    #os.environ["PLAIDML_DEVICE_IDS"] = "opencl_nvidia_geforce_gtx_1060_6gb.0"
    #import keras
    #K = keras.backend
    #
    #image = np.random.uniform ( size=(1,256,256,3) )
    #image2 = np.random.uniform ( size=(1,256,256,3) )
    #
    #y_true = K.placeholder ( (None,) + image.shape[1:] )
    #y_pred = K.placeholder ( (None,) + image2.shape[1:] )
    #
    #def reducer(x):
    #    shape = K.shape(x)
    #    x = K.reshape(x, (-1, shape[-3] , shape[-2], shape[-1]) )
    #    y = K.depthwise_conv2d(x, K.constant(np.ones( (11,11,3,1) )), strides=(1, 1), padding='valid' )
    #    y_shape = K.shape(y)
    #    return K.reshape(y, (shape[0], y_shape[1], y_shape[2], y_shape[3] ) )
    #
    #mean0 = reducer(y_true)
    #mean1 = reducer(y_pred)
    #luminance = mean0 * mean1
    #cs = y_true * y_pred
    #
    #result = K.function([y_true, y_pred],[luminance, cs]) ([image, image2])
    #
    #print (result)
    #import code
    #code.interact(local=dict(globals(), **locals()))


    main()

"""

MobileNetV2

class Upscale(nn.ModelBase):
                def on_build(self, in_ch, out_ch, kernel_size=3 ):
                    self.conv1 = nn.Conv2D( in_ch, out_ch*4, kernel_size=kernel_size, padding='SAME')

                def forward(self, x):
                    x = self.conv1(x)
                    x = tf.nn.leaky_relu(x, 0.1)
                    x = nn.depth_to_space(x, 2)
                    return x


            class BottleNeck(nn.ModelBase):
                def on_build(self, in_ch, ch, kernel_size, t, strides, r=False, **kwargs ):

                    dc = in_ch*t

                    self.conv1 = nn.Conv2D (in_ch, dc, kernel_size=1, strides=1, padding='SAME')
                    self.frn1 = nn.FRNorm2D(dc)
                    self.tlu1 = nn.TLU(dc)

                    self.conv2 = nn.DepthwiseConv2D (dc, kernel_size=kernel_size, strides=strides, padding='SAME')
                    self.frn2 = nn.FRNorm2D(dc)
                    self.tlu2 = nn.TLU(dc)


                    self.conv3 = nn.Conv2D (dc, ch, kernel_size=1, strides=1, padding='SAME')
                    self.frn3 = nn.FRNorm2D(ch)

                    self.r = r

                def forward(self, inp):
                    x = inp

                    x = self.conv1(x)
                    x = self.frn1(x)
                    x = self.tlu1(x)

                    x = self.conv2(x)
                    x = self.frn2(x)
                    x = self.tlu2(x)

                    x = self.conv3(x)
                    x = self.frn3(x)
                    
                    if self.r:
                        x = x + inp

                    return x


            class InvResidualBlock(nn.ModelBase):
                def on_build(self, in_ch, ch, kernel_size, t, strides, n, **kwargs ):
                    self.b1 = BottleNeck(in_ch, ch, kernel_size, t, strides)

                    self.b_list = []
                    for i in range(1, n):
                        self.b_list.append ( BottleNeck(ch, ch, kernel_size, t, 1, r=True) )

                def forward(self, inp):
                    x = inp
                    x = self.b1(x)

                    for i in range(len(self.b_list)):
                        x = self.b_list[i](x)

                    return x

            class Encoder(nn.ModelBase):
                def on_build(self, in_ch, e_ch, **kwargs):
                    e_ch = e_ch // 8

                    self.conv1 = nn.Conv2D( in_ch, e_ch, kernel_size=3, strides=2, padding='SAME')
                    self.frn1 = nn.FRNorm2D(e_ch)
                    self.tlu1 = nn.TLU(e_ch)

                    self.ir1 = InvResidualBlock(e_ch, e_ch*2, kernel_size=3, t=1, strides=1, n=1)
                    self.ir2 = InvResidualBlock(e_ch*2, e_ch*3, kernel_size=3, t=6, strides=2, n=2)
                    self.ir3 = InvResidualBlock(e_ch*3, e_ch*4, kernel_size=3, t=6, strides=2, n=3)
                    self.ir4 = InvResidualBlock(e_ch*4, e_ch*8, kernel_size=3, t=6, strides=2, n=4)
                    self.ir5 = InvResidualBlock(e_ch*8, e_ch*12, kernel_size=3, t=6, strides=1, n=3)
                    self.ir6 = InvResidualBlock(e_ch*12, e_ch*20, kernel_size=3, t=6, strides=2, n=3)
                    self.ir7 = InvResidualBlock(e_ch*20, e_ch*40, kernel_size=3, t=6, strides=1, n=1)

                def forward(self, inp):
                    x = inp
                    x = self.conv1(x)
                    x = self.frn1(x)
                    x = self.tlu1(x)

                    x = self.ir1(x)
                    x = self.ir2(x)
                    x = self.ir3(x)
                    x = self.ir4(x)
                    x = self.ir5(x)
                    x = self.ir6(x)
                    x = self.ir7(x)
                    
                    return x

            lowest_dense_res = resolution // 32

            class Inter(nn.ModelBase):
                def __init__(self, in_ch, ae_ch, ae_out_ch, is_hd=False, **kwargs):
                    self.in_ch, self.ae_ch, self.ae_out_ch = in_ch, ae_ch, ae_out_ch
                    super().__init__(**kwargs)

                def on_build(self):
                    in_ch, ae_ch, ae_out_ch = self.in_ch, self.ae_ch, self.ae_out_ch
                    
                    self.conv2 = nn.Conv2D( in_ch, ae_ch, kernel_size=3, strides=1, padding='SAME')
                    self.frn2 = nn.FRNorm2D(ae_ch)
                    self.tlu2 = nn.TLU(ae_ch)
                    
                    
                    
                    self.dense1 = nn.Dense( ae_ch, ae_ch )
                    self.dense2 = nn.Dense( ae_ch, lowest_dense_res * lowest_dense_res * ae_out_ch )

                def forward(self, inp):
                    x = self.conv2(inp)
                    x = self.frn2(x)
                    x = self.tlu2(x)

                    x = nn.tf.reduce_mean (x, axis=nn.conv2d_spatial_axes, keepdims=True)

                    x = nn.flatten(x)
                    
                    x = self.dense1(x)
                    x = self.dense2(x)
                    x = nn.reshape_4D (x, lowest_dense_res, lowest_dense_res, self.ae_out_ch)
                    return x

                @staticmethod
                def get_code_res():
                    return lowest_dense_res

                def get_out_ch(self):
                    return self.ae_out_ch

            class Decoder(nn.ModelBase):
                def on_build(self, in_ch, d_ch, d_mask_ch, **kwargs ):
                    d_ch = d_ch // 8
                    d_mask_ch = d_mask_ch // 8
                    
                    self.conv2 = nn.Conv2D( in_ch, d_ch*40, kernel_size=3, strides=1, padding='SAME')
                    self.frn2 = nn.FRNorm2D(d_ch*40)
                    self.tlu2 = nn.TLU(d_ch*40)

                    self.ir7 = InvResidualBlock(d_ch*40, d_ch*20, kernel_size=3, t=6, strides=1, n=1)
                    self.ir6 = InvResidualBlock(d_ch*20, d_ch*12, kernel_size=3, t=6, strides=1, n=3)
                    self.ir5 = InvResidualBlock(d_ch*12, d_ch*8, kernel_size=3, t=6, strides=1, n=3)
                    self.ir4 = InvResidualBlock(d_ch*8, d_ch*4, kernel_size=3, t=6, strides=1, n=4)
                    self.ir3 = InvResidualBlock(d_ch*4, d_ch*3, kernel_size=3, t=6, strides=1, n=3)
                    self.ir2 = InvResidualBlock(d_ch*3, d_ch*2, kernel_size=3, t=6, strides=1, n=2)
                    self.ir1 = InvResidualBlock(d_ch*2, d_ch, kernel_size=3, t=1, strides=1, n=1)
                    self.out_conv  = nn.Conv2D( d_ch, 3, kernel_size=1, padding='SAME')


                    self.mir7 = InvResidualBlock(d_ch*40, d_mask_ch*20, kernel_size=3, t=6, strides=1, n=1)
                    self.mir6 = InvResidualBlock(d_mask_ch*20, d_mask_ch*12, kernel_size=3, t=6, strides=1, n=1)
                    self.mir5 = InvResidualBlock(d_mask_ch*12, d_mask_ch*8, kernel_size=3, t=6, strides=1, n=1)
                    self.mir4 = InvResidualBlock(d_mask_ch*8, d_mask_ch*4, kernel_size=3, t=6, strides=1, n=1)
                    self.mir3 = InvResidualBlock(d_mask_ch*4, d_mask_ch*3, kernel_size=3, t=6, strides=1, n=1)
                    self.mir2 = InvResidualBlock(d_mask_ch*3, d_mask_ch*2, kernel_size=3, t=6, strides=1, n=1)
                    self.mir1 = InvResidualBlock(d_mask_ch*2, d_mask_ch, kernel_size=3, t=1, strides=1, n=1)
                    self.out_convm  = nn.Conv2D( d_mask_ch, 1, kernel_size=1, padding='SAME')


                def forward(self, inp):
                    x = inp

                    x = self.conv2(x)
                    x = self.frn2(x)
                    x = z = self.tlu2(x)

                    x = self.ir7(x)
                    x = nn.upsample2d(x)
                    x = self.ir6(x)
                    x = self.ir5(x)
                    x = nn.upsample2d(x)
                    x = self.ir4(x)
                    x = nn.upsample2d(x)
                    x = self.ir3(x)
                    x = nn.upsample2d(x)
                    x = self.ir2(x)
                    x = nn.upsample2d(x)
                    x = self.ir1(x)

                    m = self.mir7(z)
                    m = nn.upsample2d(m)
                    m = self.mir6(m)
                    m = self.mir5(m)
                    m = nn.upsample2d(m)
                    m = self.mir4(m)
                    m = nn.upsample2d(m)
                    m = self.mir3(m)
                    m = nn.upsample2d(m)
                    m = self.mir2(m)
                    m = nn.upsample2d(m)
                    m = self.mir1(m)

                    return tf.nn.sigmoid(self.out_conv(x)), \
                           tf.nn.sigmoid(self.out_convm(m))

"""