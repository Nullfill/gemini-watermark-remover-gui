# -*- coding: utf-8 -*-
"""
Integrated ProPainter Inference Engine.
Designed for Windows with real-time progress callbacks, cancellation,
and microsecond-exact PTS timestamp preservation.
"""
from fractions import Fraction
import os
from pathlib import Path
import sys
from typing import Callable, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image
import scipy.ndimage
import torch

# Ensure local modules are found
_pkg_dir = Path(__file__).resolve().parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

from model.modules.flow_comp_raft import RAFT_bi
from model.propainter import InpaintGenerator
from model.recurrent_flow_completion import RecurrentFlowCompleteNet
import torchvision.transforms.functional as TF
import av


class to_tensors:
    """Convert list of PIL images to tensor [T, C, H, W] in [0, 1]."""
    def __call__(self, frames: List[Image.Image]) -> torch.Tensor:
        return torch.stack([TF.to_tensor(f) for f in frames], dim=0)


def _binary_mask(mask: np.ndarray, th: float = 0.1) -> np.ndarray:
    out = np.zeros_like(mask, dtype=np.uint8)
    out[mask > th] = 1
    return out


def _read_mask(mpath: Union[str, Path], length: int, size: Tuple[int, int], flow_mask_dilates: int = 8, mask_dilates: int = 5):
    mpath = Path(mpath)
    if mpath.is_file():
        masks_img = [Image.open(str(mpath))]
    else:
        mnames = sorted(os.listdir(str(mpath)))
        masks_img = [Image.open(str(mpath / mp)) for mp in mnames]

    flow_masks = []
    masks_dilated = []

    for mask_img in masks_img:
        if size is not None:
            mask_img = mask_img.resize(size, Image.NEAREST)
        mask_arr = np.array(mask_img.convert('L'))

        if flow_mask_dilates > 0:
            flow_mask_img = scipy.ndimage.binary_dilation(mask_arr, iterations=flow_mask_dilates).astype(np.uint8)
        else:
            flow_mask_img = _binary_mask(mask_arr).astype(np.uint8)
        flow_masks.append(Image.fromarray(flow_mask_img * 255))

        if mask_dilates > 0:
            mask_dilated_img = scipy.ndimage.binary_dilation(mask_arr, iterations=mask_dilates).astype(np.uint8)
        else:
            mask_dilated_img = _binary_mask(mask_arr).astype(np.uint8)
        masks_dilated.append(Image.fromarray(mask_dilated_img * 255))

    if len(masks_img) == 1:
        flow_masks = flow_masks * length
        masks_dilated = masks_dilated * length

    return flow_masks, masks_dilated


def _get_ref_index(mid_neighbor_id: int, neighbor_ids: List[int], length: int, ref_stride: int = 10, ref_num: int = -1) -> List[int]:
    ref_index = []
    if ref_num == -1:
        for i in range(0, length, ref_stride):
            if i not in neighbor_ids:
                ref_index.append(i)
    else:
        start_idx = max(0, mid_neighbor_id - ref_stride * (ref_num // 2))
        end_idx = min(length, mid_neighbor_id + ref_stride * (ref_num // 2))
        for i in range(start_idx, end_idx, ref_stride):
            if i not in neighbor_ids:
                if len(ref_index) > ref_num:
                    break
                ref_index.append(i)
    return ref_index


def inpaint_crop_video(
    video_path: Union[str, Path],
    mask_path: Union[str, Path],
    output_path: Union[str, Path],
    models_dir: Union[str, Path],
    device: Optional[torch.device] = None,
    dilation: int = 6,
    raft_iter: int = 8,
    subvideo_length: int = 50,
    neighbor_length: int = 6,
    ref_stride: int = 10,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Run ProPainter inpainting on a cropped window video and save output with exact PTS.
    """
    video_path = Path(video_path)
    mask_path = Path(mask_path)
    output_path = Path(output_path)
    models_dir = Path(models_dir)

    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def check_cancel():
        if cancel_check and cancel_check():
            raise InterruptedError("Processing was cancelled by the user.")

    # 1. Read input frames & extract exact PTS timestamps
    check_cancel()
    if progress_callback:
        progress_callback("Reading cropped frames", 0, 100)

    container = av.open(str(video_path))
    vstream = container.streams.video[0]
    orig_time_base = vstream.time_base or Fraction(1, 60000)
    orig_fps = vstream.average_rate or 24

    frames_pil: List[Image.Image] = []
    pts_list: List[Optional[int]] = []

    for frame in container.decode(vstream):
        check_cancel()
        pts_list.append(frame.pts)
        arr = frame.to_ndarray(format='rgb24')
        frames_pil.append(Image.fromarray(arr))
    container.close()

    video_length = len(frames_pil)
    if video_length == 0:
        raise ValueError(f"No video frames decoded from {video_path}")

    w, h = frames_pil[0].size
    # Size must be multiple of 8
    pw = w - (w % 8)
    ph = h - (h % 8)
    if (pw, ph) != (w, h):
        frames_pil = [f.resize((pw, ph), Image.BILINEAR) for f in frames_pil]
        w, h = pw, ph

    size = (w, h)

    # 2. Read and dilate masks
    check_cancel()
    flow_masks, masks_dilated = _read_mask(
        mask_path, video_length, size,
        flow_mask_dilates=dilation,
        mask_dilates=dilation
    )

    frames_inp = [np.array(f).astype(np.uint8) for f in frames_pil]
    frames_t = to_tensors()(frames_pil).unsqueeze(0) * 2 - 1
    flow_masks_t = to_tensors()(flow_masks).unsqueeze(0)
    masks_dilated_t = to_tensors()(masks_dilated).unsqueeze(0)

    frames_t = frames_t.to(device)
    flow_masks_t = flow_masks_t.to(device)
    masks_dilated_t = masks_dilated_t.to(device)

    # 3. Load model checkpoints from models_dir
    check_cancel()
    if progress_callback:
        progress_callback("Loading neural network models", 5, 100)

    raft_path = models_dir / "raft-things.pth"
    recurrent_path = models_dir / "recurrent_flow_completion.pth"
    propainter_path = models_dir / "ProPainter.pth"

    for p in (raft_path, recurrent_path, propainter_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing required model weights file: {p}")

    fix_raft = RAFT_bi(str(raft_path), device)
    fix_flow_complete = RecurrentFlowCompleteNet(str(recurrent_path))
    for p in fix_flow_complete.parameters():
        p.requires_grad = False
    fix_flow_complete.to(device)
    fix_flow_complete.eval()

    model = InpaintGenerator(model_path=str(propainter_path)).to(device)
    model.eval()

    use_half = (device.type == 'cuda')
    if use_half:
        frames_t = frames_t.half()
        flow_masks_t = flow_masks_t.half()
        masks_dilated_t = masks_dilated_t.half()
        fix_flow_complete = fix_flow_complete.half()
        model = model.half()

    # 4. ProPainter inference
    with torch.no_grad():
        # ---- Step A: Optical Flow ----
        check_cancel()
        if frames_t.size(-1) <= 640:
            short_clip_len = 12
        elif frames_t.size(-1) <= 720:
            short_clip_len = 8
        elif frames_t.size(-1) <= 1280:
            short_clip_len = 4
        else:
            short_clip_len = 2

        if frames_t.size(1) > short_clip_len:
            gt_flows_f_list, gt_flows_b_list = [], []
            chunks_total = len(range(0, video_length, short_clip_len))
            for chunk_idx, f in enumerate(range(0, video_length, short_clip_len)):
                check_cancel()
                if progress_callback:
                    pct_flow = 10 + int(25 * (chunk_idx / max(1, chunks_total)))
                    progress_callback(f"Optical flow (frame {f + 1}/{video_length})", pct_flow, 100)
                end_f = min(video_length, f + short_clip_len)
                if f == 0:
                    flows_f, flows_b = fix_raft(frames_t[:, f:end_f], iters=raft_iter)
                else:
                    flows_f, flows_b = fix_raft(frames_t[:, f - 1:end_f], iters=raft_iter)
                gt_flows_f_list.append(flows_f)
                gt_flows_b_list.append(flows_b)
                if device.type == 'cuda':
                    torch.cuda.empty_cache()
            gt_flows_f = torch.cat(gt_flows_f_list, dim=1)
            gt_flows_b = torch.cat(gt_flows_b_list, dim=1)
            gt_flows_bi = (gt_flows_f, gt_flows_b)
        else:
            gt_flows_bi = fix_raft(frames_t, iters=raft_iter)
            if device.type == 'cuda':
                torch.cuda.empty_cache()

        if use_half:
            gt_flows_bi = (gt_flows_bi[0].half(), gt_flows_bi[1].half())

        # ---- Step B: Complete Flow ----
        check_cancel()
        flow_length = gt_flows_bi[0].size(1)
        if flow_length > subvideo_length:
            pred_flows_f, pred_flows_b = [], []
            pad_len = 5
            b_chunks = len(range(0, flow_length, subvideo_length))
            for b_idx, f in enumerate(range(0, flow_length, subvideo_length)):
                check_cancel()
                if progress_callback:
                    pct_b = 35 + int(15 * (b_idx / max(1, b_chunks)))
                    progress_callback(f"Completing motion flow ({b_idx + 1}/{b_chunks})", pct_b, 100)
                s_f = max(0, f - pad_len)
                e_f = min(flow_length, f + subvideo_length + pad_len)
                pad_len_s = max(0, f) - s_f
                pad_len_e = e_f - min(flow_length, f + subvideo_length)
                pred_flows_bi_sub, _ = fix_flow_complete.forward_bidirect_flow(
                    (gt_flows_bi[0][:, s_f:e_f], gt_flows_bi[1][:, s_f:e_f]),
                    flow_masks_t[:, s_f:e_f + 1]
                )
                pred_flows_bi_sub = fix_flow_complete.combine_flow(
                    (gt_flows_bi[0][:, s_f:e_f], gt_flows_bi[1][:, s_f:e_f]),
                    pred_flows_bi_sub,
                    flow_masks_t[:, s_f:e_f + 1]
                )
                pred_flows_f.append(pred_flows_bi_sub[0][:, pad_len_s:e_f - s_f - pad_len_e])
                pred_flows_b.append(pred_flows_bi_sub[1][:, pad_len_s:e_f - s_f - pad_len_e])
                if device.type == 'cuda':
                    torch.cuda.empty_cache()
            pred_flows_f = torch.cat(pred_flows_f, dim=1)
            pred_flows_b = torch.cat(pred_flows_b, dim=1)
            pred_flows_bi = (pred_flows_f, pred_flows_b)
        else:
            pred_flows_bi, _ = fix_flow_complete.forward_bidirect_flow(gt_flows_bi, flow_masks_t)
            pred_flows_bi = fix_flow_complete.combine_flow(gt_flows_bi, pred_flows_bi, flow_masks_t)
            if device.type == 'cuda':
                torch.cuda.empty_cache()

        # ---- Step C: Image Propagation ----
        check_cancel()
        masked_frames = frames_t * (1 - masks_dilated_t)
        subvideo_length_img_prop = min(100, subvideo_length)
        if video_length > subvideo_length_img_prop:
            updated_frames, updated_masks = [], []
            pad_len = 10
            c_chunks = len(range(0, video_length, subvideo_length_img_prop))
            for c_idx, f in enumerate(range(0, video_length, subvideo_length_img_prop)):
                check_cancel()
                if progress_callback:
                    pct_c = 50 + int(10 * (c_idx / max(1, c_chunks)))
                    progress_callback(f"Propagating textures ({c_idx + 1}/{c_chunks})", pct_c, 100)
                s_f = max(0, f - pad_len)
                e_f = min(video_length, f + subvideo_length_img_prop + pad_len)
                pad_len_s = max(0, f) - s_f
                pad_len_e = e_f - min(video_length, f + subvideo_length_img_prop)

                b, t, _, _, _ = masks_dilated_t[:, s_f:e_f].size()
                pred_flows_bi_sub = (pred_flows_bi[0][:, s_f:e_f - 1], pred_flows_bi[1][:, s_f:e_f - 1])
                prop_imgs_sub, updated_local_masks_sub = model.img_propagation(
                    masked_frames[:, s_f:e_f],
                    pred_flows_bi_sub,
                    masks_dilated_t[:, s_f:e_f],
                    'nearest'
                )
                updated_frames_sub = frames_t[:, s_f:e_f] * (1 - masks_dilated_t[:, s_f:e_f]) + \
                                     prop_imgs_sub.view(b, t, 3, h, w) * masks_dilated_t[:, s_f:e_f]
                updated_masks_sub = updated_local_masks_sub.view(b, t, 1, h, w)

                updated_frames.append(updated_frames_sub[:, pad_len_s:e_f - s_f - pad_len_e])
                updated_masks.append(updated_masks_sub[:, pad_len_s:e_f - s_f - pad_len_e])
                if device.type == 'cuda':
                    torch.cuda.empty_cache()
            updated_frames = torch.cat(updated_frames, dim=1)
            updated_masks = torch.cat(updated_masks, dim=1)
        else:
            b, t, _, _, _ = masks_dilated_t.size()
            prop_imgs, updated_local_masks = model.img_propagation(masked_frames, pred_flows_bi, masks_dilated_t, 'nearest')
            updated_frames = frames_t * (1 - masks_dilated_t) + prop_imgs.view(b, t, 3, h, w) * masks_dilated_t
            updated_masks = updated_local_masks.view(b, t, 1, h, w)
            if device.type == 'cuda':
                torch.cuda.empty_cache()
        else:
            b, t, _, _, _ = masks_dilated_t.size()
            prop_imgs, updated_local_masks = model.img_propagation(masked_frames, pred_flows_bi, masks_dilated_t, 'nearest')
            updated_frames = frames_t * (1 - masks_dilated_t) + prop_imgs.view(b, t, 3, h, w) * masks_dilated_t
            updated_masks = updated_local_masks.view(b, t, 1, h, w)
            if device.type == 'cuda':
                torch.cuda.empty_cache()

        # ---- Step D: Transformer Feature Propagation ----
        check_cancel()
        comp_frames = [None] * video_length
        neighbor_stride = max(1, neighbor_length // 2)
        ref_num = (subvideo_length // ref_stride) if (video_length > subvideo_length) else -1

        total_steps = len(range(0, video_length, neighbor_stride))
        for step_idx, f in enumerate(range(0, video_length, neighbor_stride)):
            check_cancel()
            pct = 60 + int(35 * (step_idx / max(1, total_steps)))
            if progress_callback:
                progress_callback(f"Transformer inpainting ({step_idx + 1}/{total_steps})", pct, 100)

            neighbor_ids = [
                i for i in range(max(0, f - neighbor_stride), min(video_length, f + neighbor_stride + 1))
            ]
            ref_ids = _get_ref_index(f, neighbor_ids, video_length, ref_stride, ref_num)
            selected_imgs = updated_frames[:, neighbor_ids + ref_ids, :, :, :]
            selected_masks = masks_dilated_t[:, neighbor_ids + ref_ids, :, :, :]
            selected_update_masks = updated_masks[:, neighbor_ids + ref_ids, :, :, :]
            selected_pred_flows_bi = (
                pred_flows_bi[0][:, neighbor_ids[:-1], :, :, :],
                pred_flows_bi[1][:, neighbor_ids[:-1], :, :, :]
            )

            l_t = len(neighbor_ids)
            pred_img = model(selected_imgs, selected_pred_flows_bi, selected_masks, selected_update_masks, l_t)
            pred_img = pred_img.view(-1, 3, h, w)
            pred_img = (pred_img + 1) / 2
            pred_img = pred_img.cpu().permute(0, 2, 3, 1).float().numpy() * 255.0

            binary_masks = masks_dilated_t[0, neighbor_ids, :, :, :].cpu().permute(0, 2, 3, 1).float().numpy()

            for i in range(len(neighbor_ids)):
                idx = neighbor_ids[i]
                img = np.array(pred_img[i]).astype(np.uint8) * binary_masks[i] + \
                      frames_inp[idx] * (1 - binary_masks[i])
                if comp_frames[idx] is None:
                    comp_frames[idx] = img
                else:
                    comp_frames[idx] = comp_frames[idx].astype(np.float32) * 0.5 + img.astype(np.float32) * 0.5
                comp_frames[idx] = comp_frames[idx].astype(np.uint8)

            if device.type == 'cuda':
                torch.cuda.empty_cache()

    # 5. Write output patch video with exact PTS timestamps!
    check_cancel()
    if progress_callback:
        progress_callback("Writing lossless inpaint patch", 96, 100)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_container = av.open(str(output_path), mode='w')
    out_stream = out_container.add_stream('libx264', rate=orig_fps)
    out_stream.width = w
    out_stream.height = h
    out_stream.pix_fmt = 'yuv420p'
    out_stream.time_base = orig_time_base
    out_stream.options = {'crf': '0', 'preset': 'veryfast'}

    for idx in range(video_length):
        check_cancel()
        frame_rgb = comp_frames[idx]
        if frame_rgb is None:
            frame_rgb = frames_inp[idx]
        new_frame = av.VideoFrame.from_ndarray(frame_rgb, format='rgb24')
        if idx < len(pts_list) and pts_list[idx] is not None:
            new_frame.pts = pts_list[idx]
        for packet in out_stream.encode(new_frame):
            out_container.mux(packet)

    for packet in out_stream.encode():
        out_container.mux(packet)
    out_container.close()

    # Clean up PyTorch memory
    del model, fix_raft, fix_flow_complete
    del frames_t, flow_masks_t, masks_dilated_t, updated_frames, updated_masks
    if device.type == 'cuda':
        torch.cuda.empty_cache()

    if progress_callback:
        progress_callback("Inpainting completed", 100, 100)
