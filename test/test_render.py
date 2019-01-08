from gibson2.core.render.mesh_renderer.mesh_renderer_cpu import MeshRenderer
from gibson2.core.render.mesh_renderer.mesh_renderer_tensor import MeshTensorRenderer
import numpy as np
import torch
import os
from gibson2 import assets
import matplotlib.pyplot as plt

dir = os.path.join(os.path.dirname(assets.__file__), 'test')


def test_render_loading_cleaning():
    renderer = MeshRenderer(width=800, height=600)
    renderer.release()


def test_tensor_render_loading_cleaning():
    renderer = MeshTensorRenderer(width=800, height=600)
    renderer.release()


def test_render_rendering():
    renderer = MeshRenderer(width=800, height=600)
    renderer.load_object(os.path.join(dir, 'mesh/bed1a77d92d64f5cbbaaae4feed64ec1_new.obj'))
    renderer.add_instance(0)
    renderer.set_camera([0, 0, 1.2], [0, 1, 1.2], [0, 1, 0])
    renderer.set_fov(90)
    rgb, _, seg, _ = renderer.render()
    # plt.imshow(np.concatenate([rgb, seg], axis=1)) # uncomment these two lines to show the rendering results
    # plt.show()
    assert (np.allclose(np.mean(rgb, axis=(0, 1)), np.array([0.51661223, 0.5035339, 0.4777793, 1.]), rtol=1e-3))
    assert (np.allclose(np.mean(seg, axis=(0, 1)), np.array([0.2544375, 0.5183667, 0.22600625, 1.]), rtol=1e-3))
    renderer.release()


def test_tensor_render_rendering():
    w = 800
    h = 600
    renderer = MeshTensorRenderer(w, h)
    renderer.load_object(os.path.join(dir, 'mesh/bed1a77d92d64f5cbbaaae4feed64ec1_new.obj'))
    renderer.set_camera([0, 0, 1.2], [0, 1, 1.2], [0, 1, 0])
    renderer.set_fov(90)
    tensor = torch.cuda.ByteTensor(h, w, 4)
    tensor2 = torch.cuda.ByteTensor(h, w, 4)
    renderer.render(tensor, tensor2)

    img_np = tensor.flip(0).data.cpu().numpy().reshape(h, w, 4)
    img_np2 = tensor2.flip(0).data.cpu().numpy().reshape(h, w, 4)
    # plt.imshow(np.concatenate([img_np, img_np2], axis=1))
    # plt.show()
    assert (np.allclose(np.mean(img_np.astype(np.float32), axis=(0, 1)),
                        np.array([131.71548, 128.34981, 121.81708, 255.86292]), rtol=1e-3))
    assert (np.allclose(np.mean(img_np2.astype(np.float32), axis=(0, 1)), np.array([154.2405, 0., 0., 255.86292]),
                        rtol=1e-3))
    # print(np.mean(img_np.astype(np.float32), axis = (0,1)))
    # print(np.mean(img_np2.astype(np.float32), axis = (0,1)))
    renderer.release()