# Copyright 2018 Po-Hsun Su

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import torch
import functools
import torch.nn.functional as F
from torch.autograd import Variable
import numpy as np
from math import exp

def gaussian(window_size, sigma):
    gauss = torch.Tensor([exp(-(x - window_size//2)**2/float(2*sigma**2)) for x in range(window_size)])
    return gauss/gauss.sum()

def create_window(window_size, channel):
    _1D_window = gaussian(window_size, 1.5).unsqueeze(1)
    _2D_window = _1D_window.mm(_1D_window.t()).float().unsqueeze(0).unsqueeze(0)
    window = Variable(_2D_window.expand(channel, 1, window_size, window_size).contiguous())
    return window

C1 = 0.01**2
C2 = 0.03**2

def ssim_components(img1, img2, window, window_size, channel, return_l = True):
    mu1 = F.conv2d(img1, window, padding = window_size//2, groups = channel)
    mu2 = F.conv2d(img2, window, padding = window_size//2, groups = channel)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1*mu2

    sigma1_sq = F.conv2d(img1*img1, window, padding = window_size//2, groups = channel) - mu1_sq
    sigma2_sq = F.conv2d(img2*img2, window, padding = window_size//2, groups = channel) - mu2_sq
    sigma12 = F.conv2d(img1*img2, window, padding = window_size//2, groups = channel) - mu1_mu2

    ssim_cs = (2 * sigma12 + C2) / (sigma1_sq + sigma2_sq + C2)
    if return_l:
        ssim_l = (2 * mu1_mu2 + C1) / (mu1_sq + mu2_sq + C1)
        return ssim_l, ssim_cs
    else:
        return ssim_cs

def _ssim(img1, img2, window, window_size, channel, size_average = True):
    ssim_l, ssim_cs = ssim_components(img1, img2, window, window_size, channel)
    ssim_map = ssim_l * ssim_cs

    if size_average:
        return ssim_map.mean()
    else:
        return ssim_map.mean(1).mean(1).mean(1)

def _msssim(img1, img2, window, window_size, channel, size_average = True, scales = 4):
    ssim_cs = ssim_components(img1, img2, window, window_size, channel, return_l = False)
    for i in range(1, scales - 1):
        img1, img2 = torch.nn.functional.avg_pool2d(img1, 2), torch.nn.functional.avg_pool2d(img2, 2)
        ssim_cs = torch.nn.functional.avg_pool2d(ssim_cs, 2)
        ssim_cs *= ssim_components(img1, img2, window, window_size, channel, return_l = False)

    ssim_l, ssim_cs_new = ssim_components(img1, img2, window, window_size, channel)
    ssim_map = ssim_cs * (ssim_cs_new * ssim_l)

    if size_average:
        return ssim_map.mean()
    else:
        return ssim_map.mean(1).mean(1).mean(1)

class AbstractSSIM(torch.nn.Module):
    def __init__(self, window_size = 11, size_average = True):
        super().__init__()
        self.window_size = window_size
        self.size_average = size_average
        self.channel = 1
        self.window = create_window(window_size, self.channel)
        self.backend = None

    def forward(self, img1, img2):
        (_, channel, _, _) = img1.size()

        if channel == self.channel and self.window.data.type() == img1.data.type():
            window = self.window
        else:
            window = create_window(self.window_size, channel)

            if img1.is_cuda:
                window = window.cuda(img1.get_device())
            window = window.type_as(img1)

            self.window = window
            self.channel = channel

        return self.backend(img1, img2, window, self.window_size, channel, self.size_average)

class SSIM(AbstractSSIM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = _ssim

class MSSSIM(AbstractSSIM):
    def __init__(self, scales = 5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = functools.partial(_msssim, scales = scales)

def ssim(img1, img2, window_size = 11, size_average = True):
    (_, channel, _, _) = img1.size()
    window = create_window(window_size, channel)

    if img1.is_cuda:
        window = window.cuda(img1.get_device())
    window = window.type_as(img1)

    return _ssim(img1, img2, window, window_size, channel, size_average)
