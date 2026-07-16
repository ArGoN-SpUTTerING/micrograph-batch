"""Interactive Tkinter tool for drawing crop boxes and saving them to the CSV."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

try:
    import tkinter as tk
    from tkinter import messagebox
    from PIL import ImageTk
except ImportError:
    tk = None
    messagebox = None
    ImageTk = None

from micrograph_batch.batch import run_batch
from micrograph_batch.config import (
    ConfigEntry,
    build_task_from_row,
    load_config_entries,
    load_tasks,
    update_row_crop,
    write_config_table,
)
from micrograph_batch.constants import RESAMPLE_LANCZOS
from micrograph_batch.imaging import (
    boxes_equal,
    clamp,
    clamp_crop_box,
    crop_box_to_xywh,
    prepare_image_for_jpeg,
    xywh_to_crop_box,
)


@dataclass
class PreviewState:
    scale: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    display_width: int = 1
    display_height: int = 1


class VisualCropConfigApp:
    def __init__(
        self,
        config_path: Path,
        fieldnames: list[str],
        rows: list[dict[str, str]],
        entries: list[ConfigEntry],
        input_dir: Path,
        output_dir: Path,
    ) -> None:
        if tk is None or ImageTk is None or messagebox is None:
            raise RuntimeError("Visual crop mode requires Tkinter and Pillow ImageTk.")

        self.config_path = config_path
        self.fieldnames = fieldnames
        self.rows = rows
        self.entries = entries
        self.input_dir = input_dir
        self.output_dir = output_dir

        self.current_index = 0
        self.original_image: Image.Image | None = None
        self.preview_photo = None
        self.preview_state = PreviewState()
        self.selection_box: tuple[int, int, int, int] | None = None
        self.drag_start: tuple[int, int] | None = None
        self.closed_with_unsaved_changes = False

        self.root = tk.Tk()
        self.root.title("Micrograph Batch Visual Crop")
        self.root.geometry("1320x940")
        self.root.minsize(960, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

        self.header_var = tk.StringVar()
        self.selection_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.message_var = tk.StringVar(value="Drag on the image to create a crop box, then press S to save.")
        self.box_x_var = tk.StringVar()
        self.box_y_var = tk.StringVar()
        self.box_w_var = tk.StringVar()
        self.box_h_var = tk.StringVar()

        self._build_ui()
        self._bind_events()
        self._load_current_image()

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self.root, padx=10, pady=8)
        toolbar.pack(fill="x")

        tk.Button(toolbar, text="Previous", width=12, command=self.show_previous_image).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Next", width=12, command=self.show_next_image).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Reset Box", width=12, command=self.clear_selection).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Save Crop", width=12, command=self.save_current_crop).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Clear Saved", width=12, command=self.clear_saved_crop).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="Save + Next", width=12, command=lambda: self.save_current_crop(go_next=True)).pack(
            side="left",
            padx=(0, 8),
        )

        instruction = (
            "Shortcuts: Left/Right switch image, S save crop, Enter save and next, "
            "R reset selection, C clear saved crop, Ctrl+Arrow move box, Esc quit."
        )
        tk.Label(toolbar, text=instruction, anchor="w").pack(side="left", fill="x", expand=True)

        adjust_frame = tk.Frame(self.root, padx=10, pady=0)
        adjust_frame.pack(fill="x", pady=(0, 8))

        tk.Label(adjust_frame, text="X").pack(side="left")
        tk.Entry(adjust_frame, textvariable=self.box_x_var, width=8).pack(side="left", padx=(4, 10))
        tk.Label(adjust_frame, text="Y").pack(side="left")
        tk.Entry(adjust_frame, textvariable=self.box_y_var, width=8).pack(side="left", padx=(4, 10))
        tk.Label(adjust_frame, text="W").pack(side="left")
        tk.Entry(adjust_frame, textvariable=self.box_w_var, width=8).pack(side="left", padx=(4, 10))
        tk.Label(adjust_frame, text="H").pack(side="left")
        tk.Entry(adjust_frame, textvariable=self.box_h_var, width=8).pack(side="left", padx=(4, 10))
        tk.Button(adjust_frame, text="Apply Box", width=12, command=self.apply_box_from_inputs).pack(
            side="left",
            padx=(0, 8),
        )
        tk.Button(adjust_frame, text="Left 1", width=8, command=lambda: self.nudge_box(-1, 0)).pack(
            side="left",
            padx=(0, 4),
        )
        tk.Button(adjust_frame, text="Right 1", width=8, command=lambda: self.nudge_box(1, 0)).pack(
            side="left",
            padx=(0, 4),
        )
        tk.Button(adjust_frame, text="Up 1", width=8, command=lambda: self.nudge_box(0, -1)).pack(
            side="left",
            padx=(0, 4),
        )
        tk.Button(adjust_frame, text="Down 1", width=8, command=lambda: self.nudge_box(0, 1)).pack(
            side="left",
            padx=(0, 8),
        )
        tk.Label(
            adjust_frame,
            text="You can drag a box, then fine-tune X/Y/W/H and click Apply Box.",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        self.canvas = tk.Canvas(self.root, bg="#1e1e1e", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        info_frame = tk.Frame(self.root, padx=10, pady=8)
        info_frame.pack(fill="x")

        tk.Label(info_frame, textvariable=self.header_var, anchor="w", justify="left").pack(fill="x")
        tk.Label(info_frame, textvariable=self.selection_var, anchor="w", justify="left").pack(fill="x", pady=(4, 0))
        tk.Label(info_frame, textvariable=self.output_var, anchor="w", justify="left", wraplength=1240).pack(
            fill="x",
            pady=(4, 0),
        )
        tk.Label(info_frame, textvariable=self.message_var, anchor="w", justify="left", wraplength=1240).pack(
            fill="x",
            pady=(4, 0),
        )

    def _bind_events(self) -> None:
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.bind("<Left>", lambda _event: self.show_previous_image())
        self.root.bind("<Right>", lambda _event: self.show_next_image())
        self.root.bind("<s>", lambda _event: self.save_current_crop())
        self.root.bind("<S>", lambda _event: self.save_current_crop())
        self.root.bind("<Return>", lambda _event: self.save_current_crop(go_next=True))
        self.root.bind("<r>", lambda _event: self.clear_selection())
        self.root.bind("<R>", lambda _event: self.clear_selection())
        self.root.bind("<c>", lambda _event: self.clear_saved_crop())
        self.root.bind("<C>", lambda _event: self.clear_saved_crop())
        self.root.bind("<Control-Left>", lambda _event: self.move_selection(-1, 0))
        self.root.bind("<Control-Right>", lambda _event: self.move_selection(1, 0))
        self.root.bind("<Control-Up>", lambda _event: self.move_selection(0, -1))
        self.root.bind("<Control-Down>", lambda _event: self.move_selection(0, 1))
        self.root.bind("<Control-Shift-Left>", lambda _event: self.move_selection(-10, 0))
        self.root.bind("<Control-Shift-Right>", lambda _event: self.move_selection(10, 0))
        self.root.bind("<Control-Shift-Up>", lambda _event: self.move_selection(0, -10))
        self.root.bind("<Control-Shift-Down>", lambda _event: self.move_selection(0, 10))
        self.root.bind("<Escape>", lambda _event: self.close_window())

    def _current_entry(self) -> ConfigEntry:
        return self.entries[self.current_index]

    def _current_image_size(self) -> tuple[int, int]:
        if self.original_image is None:
            return 0, 0
        return self.original_image.size

    def _set_box_inputs_from_selection(self) -> None:
        xywh = crop_box_to_xywh(self.selection_box)
        if xywh is None:
            self.box_x_var.set("")
            self.box_y_var.set("")
            self.box_w_var.set("")
            self.box_h_var.set("")
            return

        x, y, width, height = xywh
        self.box_x_var.set(str(x))
        self.box_y_var.set(str(y))
        self.box_w_var.set(str(width))
        self.box_h_var.set(str(height))

    def _has_unsaved_changes(self) -> bool:
        entry = self._current_entry()
        return not boxes_equal(self.selection_box, entry.task.crop_box)

    def _prompt_save_before_navigation(self, action_label: str) -> bool:
        if not self._has_unsaved_changes():
            return True

        answer = messagebox.askyesnocancel(
            "Unsaved crop changes",
            (
                f"You have unsaved crop changes for {self._current_entry().task.source_path.name}.\n\n"
                f"Yes: save before {action_label}\n"
                "No: discard current unsaved edits\n"
                "Cancel: stay on this image"
            ),
        )
        if answer is None:
            return False
        if answer:
            self.save_current_crop()
        else:
            self.selection_box = self._current_entry().task.crop_box
            self._draw_overlay()
        return True

    def close_window(self) -> None:
        if not self._prompt_save_before_navigation("closing"):
            return
        self.root.destroy()

    def _load_current_image(self) -> None:
        entry = self._current_entry()
        self.original_image = prepare_image_for_jpeg(entry.task.source_path)
        self.selection_box = entry.task.crop_box
        self.drag_start = None
        self._set_box_inputs_from_selection()

        self.message_var.set(f"Loaded: {entry.task.source_path}")
        self.root.title(
            f"Micrograph Batch Visual Crop - {entry.task.source_path.name} "
            f"({self.current_index + 1}/{len(self.entries)})"
        )
        self._refresh_labels()
        self.root.after_idle(self._render_preview)

    def _on_canvas_resize(self, _event=None) -> None:
        if self.original_image is not None:
            self._render_preview()

    def _render_preview(self) -> None:
        if self.original_image is None:
            return

        canvas_width = max(self.canvas.winfo_width(), 200)
        canvas_height = max(self.canvas.winfo_height(), 200)
        image_width, image_height = self.original_image.size
        scale = min(canvas_width / image_width, canvas_height / image_height)
        scale = max(scale, 0.01)

        display_width = max(1, int(image_width * scale))
        display_height = max(1, int(image_height * scale))
        offset_x = (canvas_width - display_width) // 2
        offset_y = (canvas_height - display_height) // 2

        preview_image = self.original_image.resize((display_width, display_height), RESAMPLE_LANCZOS)
        if preview_image.mode not in {"RGB", "RGBA", "L"}:
            preview_image = preview_image.convert("RGB")

        self.preview_photo = ImageTk.PhotoImage(preview_image)
        self.preview_state = PreviewState(
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            display_width=display_width,
            display_height=display_height,
        )

        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self.preview_photo, tags="preview")
        self._draw_overlay()

    def apply_box_from_inputs(self) -> None:
        if self.original_image is None:
            return

        try:
            x = int(self.box_x_var.get().strip())
            y = int(self.box_y_var.get().strip())
            width = int(self.box_w_var.get().strip())
            height = int(self.box_h_var.get().strip())
        except ValueError:
            self.message_var.set("X, Y, W, H must all be integers.")
            return

        if width <= 0 or height <= 0:
            self.message_var.set("W and H must be positive.")
            return

        try:
            self.selection_box = clamp_crop_box(
                xywh_to_crop_box(x, y, width, height),
                self._current_image_size(),
            )
        except ValueError as exc:
            self.message_var.set(str(exc))
            return

        self.message_var.set("Selection updated from X/Y/W/H inputs.")
        self._draw_overlay()

    def move_selection(self, dx: int, dy: int) -> None:
        if self.original_image is None or not self._box_is_valid(self.selection_box):
            self.message_var.set("Create or load a crop box before moving it.")
            return

        image_width, image_height = self._current_image_size()
        left, top, right, bottom = self.selection_box
        box_width = right - left
        box_height = bottom - top

        max_left = max(image_width - box_width, 0)
        max_top = max(image_height - box_height, 0)
        new_left = clamp(left + dx, 0, max_left)
        new_top = clamp(top + dy, 0, max_top)
        self.selection_box = (new_left, new_top, new_left + box_width, new_top + box_height)
        self.message_var.set(f"Selection moved by dx={dx}, dy={dy}.")
        self._draw_overlay()

    def nudge_box(self, dx: int, dy: int) -> None:
        self.move_selection(dx, dy)

    def _canvas_point_inside_image(self, x: int, y: int) -> bool:
        state = self.preview_state
        return (
            state.offset_x <= x <= state.offset_x + state.display_width
            and state.offset_y <= y <= state.offset_y + state.display_height
        )

    def _canvas_to_image_point(self, x: int, y: int) -> tuple[int, int]:
        if self.original_image is None:
            return 0, 0

        state = self.preview_state
        image_width, image_height = self.original_image.size
        local_x = clamp(x - state.offset_x, 0, state.display_width)
        local_y = clamp(y - state.offset_y, 0, state.display_height)

        image_x = clamp(int(round(local_x / state.scale)), 0, image_width)
        image_y = clamp(int(round(local_y / state.scale)), 0, image_height)
        return image_x, image_y

    def _image_to_canvas_box(self, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        state = self.preview_state
        left, top, right, bottom = box
        x1 = int(round(state.offset_x + left * state.scale))
        y1 = int(round(state.offset_y + top * state.scale))
        x2 = int(round(state.offset_x + right * state.scale))
        y2 = int(round(state.offset_y + bottom * state.scale))
        return x1, y1, x2, y2

    def _normalize_box(self, start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int, int, int]:
        left, right = sorted((start[0], end[0]))
        top, bottom = sorted((start[1], end[1]))
        return left, top, right, bottom

    def _box_is_valid(self, box: tuple[int, int, int, int] | None) -> bool:
        if box is None:
            return False
        left, top, right, bottom = box
        return right > left and bottom > top

    def _draw_overlay(self) -> None:
        self.canvas.delete("overlay")
        if not self._box_is_valid(self.selection_box):
            self._refresh_labels()
            return

        x1, y1, x2, y2 = self._image_to_canvas_box(self.selection_box)
        width = self.selection_box[2] - self.selection_box[0]
        height = self.selection_box[3] - self.selection_box[1]
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00d084", width=2, tags="overlay")
        self.canvas.create_text(
            x1 + 8,
            max(y1 - 6, 8),
            text=f"{width} x {height}px",
            fill="white",
            anchor="sw",
            tags="overlay",
        )
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        if self.original_image is None:
            return

        entry = self._current_entry()
        image_width, image_height = self.original_image.size
        self._set_box_inputs_from_selection()
        self.header_var.set(
            f"Image {self.current_index + 1}/{len(self.entries)} | Row {entry.row_number} | "
            f"Source: {entry.task.source_path} | Size: {image_width} x {image_height}"
        )

        if self._box_is_valid(self.selection_box):
            left, top, right, bottom = self.selection_box
            width = right - left
            height = bottom - top
            self.selection_var.set(
                f"Selection: left={left}, top={top}, right={right}, bottom={bottom} | Size: {width} x {height}"
            )
        else:
            self.selection_var.set("Selection: none. Drag with the mouse to create a crop box.")

        self.output_var.set(f"Config: {self.config_path} | Output: {entry.task.output_path}")

    def _on_mouse_down(self, event) -> None:
        if self.original_image is None or not self._canvas_point_inside_image(event.x, event.y):
            return

        self.drag_start = self._canvas_to_image_point(event.x, event.y)
        self.selection_box = None
        self._draw_overlay()

    def _on_mouse_drag(self, event) -> None:
        if self.drag_start is None or self.original_image is None:
            return

        current = self._canvas_to_image_point(event.x, event.y)
        self.selection_box = self._normalize_box(self.drag_start, current)
        self._draw_overlay()

    def _on_mouse_up(self, event) -> None:
        if self.drag_start is None or self.original_image is None:
            return

        current = self._canvas_to_image_point(event.x, event.y)
        box = self._normalize_box(self.drag_start, current)
        self.drag_start = None

        if self._box_is_valid(box):
            self.selection_box = box
            self.message_var.set("Selection updated. Press S to save it into the CSV config.")
        else:
            self.selection_box = None
            self.message_var.set("Selection cleared. Drag again to create a crop box.")

        self._draw_overlay()

    def clear_selection(self) -> None:
        self.selection_box = None
        self.message_var.set("Selection cleared locally. Press C if you also want to clear the saved crop in the CSV.")
        self._draw_overlay()

    def _change_image(self, step: int) -> None:
        if not self._prompt_save_before_navigation("switching images"):
            return

        new_index = self.current_index + step
        if not 0 <= new_index < len(self.entries):
            return

        self.current_index = new_index
        self._load_current_image()

    def show_previous_image(self) -> None:
        self._change_image(-1)

    def show_next_image(self) -> None:
        self._change_image(1)

    def _persist_current_row(self, crop_box: tuple[int, int, int, int] | None) -> None:
        entry = self._current_entry()
        update_row_crop(entry.row_data, crop_box)
        write_config_table(self.config_path, self.fieldnames, self.rows)

        refreshed_task = build_task_from_row(
            row_number=entry.row_number,
            row=entry.row_data,
            input_dir=self.input_dir,
            output_dir=self.output_dir,
        )
        if refreshed_task is None:
            raise RuntimeError("Current row became disabled or invalid while saving crop data.")
        entry.task = refreshed_task

    def save_current_crop(self, go_next: bool = False) -> None:
        if not self._box_is_valid(self.selection_box):
            self.message_var.set("Please draw a valid crop box before saving.")
            self._refresh_labels()
            return

        self._persist_current_row(self.selection_box)
        self.message_var.set(f"Crop saved to config row {self._current_entry().row_number}.")
        self._refresh_labels()

        if go_next and self.current_index < len(self.entries) - 1:
            new_index = self.current_index + 1
            if 0 <= new_index < len(self.entries):
                self.current_index = new_index
                self._load_current_image()

    def clear_saved_crop(self) -> None:
        self.selection_box = None
        self._persist_current_row(None)
        self.message_var.set(f"Saved crop cleared from config row {self._current_entry().row_number}.")
        self._draw_overlay()

    def run(self) -> None:
        self.root.mainloop()


def visual_crop_mode(
    config_path: Path,
    input_dir: Path,
    output_dir: Path,
    auto_process_after_crop: bool,
    overwrite: bool,
) -> None:
    if tk is None or ImageTk is None or messagebox is None:
        raise SystemExit("Visual crop mode requires Tkinter and Pillow ImageTk.")

    fieldnames, rows, entries = load_config_entries(
        config_path=config_path,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    if not entries:
        raise SystemExit(
            f"No enabled rows with filenames found in {config_path}. "
            "Fill the CSV first or regenerate it with --init-config."
        )

    app = VisualCropConfigApp(
        config_path=config_path,
        fieldnames=fieldnames,
        rows=rows,
        entries=entries,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    app.run()

    if auto_process_after_crop:
        print("Visual crop finished. Starting batch processing...")
        tasks = load_tasks(config_path=config_path, input_dir=input_dir, output_dir=output_dir)
        if not tasks:
            raise SystemExit(f"No enabled rows found in {config_path} after visual crop finished.")
        run_batch(tasks=tasks, overwrite=overwrite)
