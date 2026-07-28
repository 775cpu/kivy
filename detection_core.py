import math


def python_fallback_boxes(frame_bytes, width, height, threshold=120, min_area=32):
    """A lightweight detector used as a fallback when the JNI bridge is unavailable.

    It scans the Y-plane of an NV21 frame, finds bright connected regions, and
    converts them into simple bounding boxes. This keeps the app functional even
    when the native bridge is unavailable or has not initialized yet.
    """
    if not frame_bytes or width <= 0 or height <= 0:
        return []

    y_plane_len = width * height
    if len(frame_bytes) < y_plane_len:
        return []

    y_plane = frame_bytes[:y_plane_len]
    step = max(2, min(8, min(width, height) // 16))
    grid_w = max(1, (width + step - 1) // step)
    grid_h = max(1, (height + step - 1) // step)

    def brightness_at(gx, gy):
        x0 = gx * step
        y0 = gy * step
        x1 = min(width, x0 + step)
        y1 = min(height, y0 + step)
        total = 0
        count = 0
        for y in range(y0, y1):
            row_offset = y * width
            for x in range(x0, x1):
                total += y_plane[row_offset + x]
                count += 1
        return total / max(1, count)

    visited = [False] * (grid_w * grid_h)
    boxes = []

    for gy in range(grid_h):
        for gx in range(grid_w):
            idx = gy * grid_w + gx
            if visited[idx]:
                continue
            value = brightness_at(gx, gy)
            if value <= threshold:
                visited[idx] = True
                continue

            stack = [(gx, gy)]
            visited[idx] = True
            area = 0
            min_x = gx * step
            min_y = gy * step
            max_x = (gx + 1) * step
            max_y = (gy + 1) * step

            while stack:
                cx, cy = stack.pop()
                area += 1
                x0 = cx * step
                y0 = cy * step
                x1 = min(width, x0 + step)
                y1 = min(height, y0 + step)
                min_x = min(min_x, x0)
                min_y = min(min_y, y0)
                max_x = max(max_x, x1)
                max_y = max(max_y, y1)

                for ny in range(max(0, cy - 1), min(grid_h, cy + 2)):
                    for nx in range(max(0, cx - 1), min(grid_w, cx + 2)):
                        nidx = ny * grid_w + nx
                        if visited[nidx]:
                            continue
                        if brightness_at(nx, ny) > threshold:
                            visited[nidx] = True
                            stack.append((nx, ny))

            if (max_x - min_x) * (max_y - min_y) >= min_area:
                box_w = max(1, max_x - min_x)
                box_h = max(1, max_y - min_y)
                conf = min(0.99, 0.35 + (area / max(1, grid_w * grid_h)) * 0.6)
                boxes.append((float(min_x), float(min_y), float(max_x), float(max_y), conf, 0))

    boxes.sort(key=lambda item: (item[2] - item[0]) * (item[3] - item[1]), reverse=True)
    return boxes[:6]
