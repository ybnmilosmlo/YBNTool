"""
ymap_checker_sftp.py
=====================
Same idea as ymap_checker.py, but for servers you only access remotely
(e.g. through WinSCP or FileZilla). Instead of picking a local folder,
you type in the same SFTP login info you already use in WinSCP, and it
scans your resources folder directly over the network.

Requirements:
    pip install paramiko --break-system-packages     (or without the flag on Windows)

Run it with:
    python ymap_checker_sftp.py
"""

import os
import stat
import threading
import time
import base64
import math
import shlex
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import paramiko
except ImportError:
    paramiko = None

# ============================================================
# EDIT THIS LIST — same as before: exact .ymap / .ybn filenames
# that should exist (once each) somewhere inside the resources
# folder. Filenames are matched case-insensitively.
# ============================================================
ZONES = {
    "SouthSide": [
        "lr_sc1_occl_00.ymap", "lr_sc1_occl_01.ymap", "lr_sc1_occl_02.ymap", "lr_sc1_occl_03.ymap",
        "lr_sc1_rd_strm_3.ymap", "lr_sc1_rd_long_0.ymap", "lr_sc1_rd_critical_1.ymap",
        "lr_sc1_rd_strm_7.ymap", "lr_sc1_rd_critical_2.ymap", "lr_sc1_rd_strm_8.ymap"
    ],
    "East Los Santos": [
        "bkr_id1_occl_00.ymap", "bkr_id1_occl_01.ymap", "bkr_id1_occl_02.ymap", "bkr_id1_occl_03.ymap",
        "bkr_id1_rd_long_0.ymap"
    ],
    "Elysian Fields": [
        "hei_ch3_occl_00.ymap", "ch1_far_occl_00.ymap"
    ],
    "Jefferson/Las Colinas": [
        "ch1_far_occl_00.ymap", "hei_ch3_occl_00.ymap", "hei_ch3_occl_01.ymap",
        "hei_ch3_occl_02.ymap", "hei_id2_occl_03.ymap", "hei_ch3_occl_03.ymap"
    ],
    "DownTown": [
        "apa_ss1_occl_00.ymap", "apa_ss1_occl_01.ymap", "apa_ss1_occl_02.ymap", "apa_ss1_occl_03.ymap",
        "ch1_far_occl_00.ymap", "hei_bh1_occl_00.ymap", "hei_bh1_occl_02.ymap", "hei_bh1_occl_04.ymap",
        "hei_bh1_occl_05.ymap", "hei_dt1_occl_00.ymap", "hei_dt1_occl_01.ymap", "hei_dt1_occl_02.ymap",
        "hei_dt1_occl_03.ymap", "hei_dt1_occl_04.ymap", "hei_dt1_occl_06.ymap", "hei_dt1_occl_07.ymap",
        "hei_hw1_occl_01.ymap", "hei_hw1_occl_00.ymap", "hei_kt1_occl_02.ymap", "hei_kt1_occl_03.ymap",
        "hei_sm_occl_00.ymap", "hei_sm_occl_02.ymap", "hei_sm_occl_03.ymap", "vb_occl_00.ymap",
        "hei_dt1_rd1_critical_1.ymap", "hei_dt1_rd1_long_0.ymap", "bh1_14_0.ybn", "bh1_16_0.ybn",
        "hei_sm_rd_long_1.ymap", "hei_sm_rd_strm_3.ymap"
    ],
    "Beach": [
        "vb_occl_00.ymap", "vb_occl_01.ymap", "hei_vb_rd_long_0.ymap", "hei_vb_rd_strm_4.ymap"
    ],
    "Industrial": [
        "hei_po1_occl_00.ymap", "hei_po1_occl_01.ymap", "hei_po1_occl_03.ymap",
        "hei_ship_occ_grp1.ymap", "hei_ship_occ_grp2.ymap", "ship_occ_grp1.ymap", "ship_occ_grp2.ymap",
        "bkr_id1_occl_00.ymap", "bkr_id1_occl_01.ymap", "lr_sc1_occl_01.ymap"
    ],
    "VineWood": [],
    "Vinewood Lake": [
        "apa_ch2_occl_06.ymap", "apa_ch2_occl_07.ymap", "ch1_far_occl_00.ymap"
    ],
    "Del Perro": [
        "hei_sm_occl_00.ymap", "hei_sm_occl_01.ymap", "hei_sm_occl_03.ymap"
    ],
    "Pacific Bluffs": [
        "ch1_occl_00.ymap", "ch1_occl_02.ymap", "hei_ch1_occl_00.ymap", "hei_ch1_occl_02.ymap"
    ],
    "Baltimore/Philadelphia": [
        "cs4_occl_00.ymap", "cs4_occl_01.ymap", "cs4_occl_02.ymap", "cs4_occl_03.ymap",
        "cs4_occl_04.ymap", "cs4_occl_05.ymap", "cs4_occl_06.ymap", "cs4_occl_07.ymap",
        "cs1_far_occl_01.ymap"
    ],
    "Paleto": [
        "cs1_far_occl_00.ymap", "cs1_occl_07.ymap", "cs1_occl_09.ymap", "cs1_occl_10.ymap",
        "cs1_occl_11.ymap", "hei_cs1_roads_pb_strm_2.ymap"
    ],
    "Mirror Park": [
        "hei_id2_occl_03.ymap", "hei_id2_occl_02.ymap", "hei_hw1_occl_01.ymap"
    ],
}
ALL_ZONES_LABEL = "All Zones (full check)"

MAP_IMAGE_URL = "https://i.ibb.co/qFsB0dDZ/MILOSTVIMAGE.png"

# Same pixel-coordinate polygons used on the website's map (from image-map.net)
ZONE_SHAPES = {
    "SouthSide": [287,490,303,480,337,484,341,568,326,581,301,583,279,590,255,571,235,561,255,525],
    "East Los Santos": [205,602,279,613,313,610,317,663,291,678,256,684,244,646,196,640],
    "Elysian Fields": [303,683,325,708,349,731,373,745,335,745,281,727,202,709,184,684,186,658,223,681,255,686],
    "Jefferson/Las Colinas": [312,666,324,695,359,708,397,704,432,695,455,683,456,660,409,659,376,653,347,665],
    "DownTown": [349,478,349,577,435,576,480,597,505,523,497,527,465,513,478,471,469,427,431,366,391,396,404,473],
    "Beach": [330,320,380,399,361,426,332,439,341,451,310,472,275,406,252,372],
    "Industrial": [219,490,242,504,232,529,229,570,234,588,196,577,197,509],
    "VineWood": [582,573,612,571,636,589,633,622,589,622,566,600],
    "Vinewood Lake": [569,479,547,507,555,534,574,557,592,544,600,509,595,485],
    "Del Perro": [429,321,469,348,468,387,424,345],
    "Pacific Bluffs": [465,173,480,205,529,182,574,178,594,162,631,172,638,142,562,132,506,141],
    "Baltimore/Philadelphia": [882,662,876,707,867,723,837,744,823,778,818,804,852,833,898,847,948,851,981,839,951,807,914,778,924,762,940,728,895,666],
    "Paleto": [1140,468,1173,495,1207,538,1217,567,1249,539,1257,496,1213,454,1169,444],
    "Mirror Park": [463,602,510,629,518,654,479,654,384,643,382,607,425,594],
}




def sftp_walk(sftp, remote_path):
    """Recursively walk a remote SFTP directory.
    Returns dict {lowercase_filename: [full_remote_path, ...]}
    """
    index = {}

    def _walk(path):
        try:
            entries = sftp.listdir_attr(path)
        except IOError as e:
            raise RuntimeError(f"Could not read folder: {path}\n{e}")

        for entry in entries:
            full_path = path.rstrip("/") + "/" + entry.filename
            if stat.S_ISDIR(entry.st_mode):
                _walk(full_path)
            else:
                name = entry.filename
                if name.lower().endswith(".ymap") or name.lower().endswith(".ybn"):
                    index.setdefault(name.lower(), []).append(full_path)

    _walk(remote_path)
    return index


def sftp_walk_parallel(transport, remote_path, fallback_sftp, max_workers=3):
    """Like sftp_walk, but lists several folders concurrently using multiple
    SFTP channels on the same transport, instead of one at a time.
    Used when the server doesn't allow the single-command fast path
    (SFTP-only hosts) but we can still overlap some round trips.

    Some hosts strictly limit how many simultaneous channels/sessions are
    allowed. If opening a new channel fails, threads fall back to sharing
    a single already-open connection (with a lock) instead of crashing.
    """
    index = {}
    lock = threading.Lock()
    thread_local = threading.local()

    def get_sftp():
        if not hasattr(thread_local, "sftp"):
            try:
                thread_local.sftp = paramiko.SFTPClient.from_transport(transport)
            except Exception:
                thread_local.sftp = None  # signal: use the shared fallback instead
        return thread_local.sftp

    def list_dir(path):
        sftp = get_sftp()
        try:
            if sftp is not None:
                return path, sftp.listdir_attr(path)
            else:
                # Couldn't open a dedicated channel — reuse the shared one safely
                with lock:
                    return path, fallback_sftp.listdir_attr(path)
        except Exception:
            return path, []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending = {executor.submit(list_dir, remote_path)}
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                path, entries = fut.result()
                for entry in entries:
                    full_path = path.rstrip("/") + "/" + entry.filename
                    if stat.S_ISDIR(entry.st_mode):
                        pending.add(executor.submit(list_dir, full_path))
                    else:
                        name = entry.filename
                        if name.lower().endswith(".ymap") or name.lower().endswith(".ybn"):
                            with lock:
                                index.setdefault(name.lower(), []).append(full_path)

    return index


def try_remote_find(transport, remote_path, timeout=20):
    """Attempt a single fast server-side 'find' command over SSH exec.
    Much faster than sftp_walk since it's one round trip instead of
    one per subfolder. Returns the same index dict as sftp_walk, or
    None if exec access isn't available (common on SFTP-only hosts),
    so the caller can fall back to sftp_walk.
    """
    try:
        chan = transport.open_session(timeout=timeout)
        chan.settimeout(timeout)
        quoted_path = shlex.quote(remote_path)
        cmd = (
            f"find {quoted_path} -type f "
            f"\\( -iname '*.ymap' -o -iname '*.ybn' \\) 2>/dev/null"
        )
        chan.exec_command(cmd)

        stdout_file = chan.makefile("r", -1)
        output = stdout_file.read()
        exit_status = chan.recv_exit_status()
        chan.close()

        # exit_status 127 (command not found) or a connection-level failure
        # both mean we should fall back to the slower method.
        if exit_status not in (0, 1):  # 1 = find ran but found nothing, still valid
            return None

        index = {}
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            name = line.rsplit("/", 1)[-1]
            index.setdefault(name.lower(), []).append(line)
        return index

    except Exception:
        # Any failure (no exec access, timeout, etc.) — signal fallback
        return None



class SftpYmapCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YMAP Resource Checker (SFTP)")
        self.root.geometry("820x600")
        self.root.minsize(640, 460)

        self.sftp = None
        self.transport = None

        # --- Connection form ---
        form = ttk.Frame(root, padding=12)
        form.pack(fill="x")

        ttk.Label(form, text="Connect with the same info you use in WinSCP/FileZilla:",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(form, text="Host").grid(row=1, column=0, sticky="w")
        self.host_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.host_var, width=28).grid(row=1, column=1, sticky="w", padx=(4, 16))

        ttk.Label(form, text="Port").grid(row=1, column=2, sticky="w")
        self.port_var = tk.StringVar(value="22")
        ttk.Entry(form, textvariable=self.port_var, width=6).grid(row=1, column=3, sticky="w", padx=(4, 0))

        ttk.Label(form, text="Username").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.user_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.user_var, width=28).grid(row=2, column=1, sticky="w", padx=(4, 16), pady=(6, 0))

        ttk.Label(form, text="Password").grid(row=2, column=2, sticky="w", pady=(6, 0))
        self.pass_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.pass_var, width=18, show="•").grid(row=2, column=3, sticky="w", pady=(6, 0))

        ttk.Label(form, text="Which zone are you checking?").grid(row=3, column=0, sticky="w", pady=(6, 0))
        zone_names = [ALL_ZONES_LABEL] + list(ZONES.keys())
        self.zone_var = tk.StringVar(value=zone_names[0])
        self._zone_touched = False
        zone_combo = ttk.Combobox(form, textvariable=self.zone_var, values=zone_names, state="readonly", width=26)
        zone_combo.grid(row=3, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        zone_combo.bind("<<ComboboxSelected>>", lambda e: setattr(self, "_zone_touched", True))

        self.map_btn = ttk.Button(form, text="Pick Zone on Map", command=self.open_map_picker_thread)
        self.map_btn.grid(
            row=3, column=2, sticky="w", padx=(6, 0), pady=(6, 0)
        )

        ttk.Label(form, text="Resources folder (remote)").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.path_var = tk.StringVar(value="(not selected yet)")
        ttk.Label(form, textvariable=self.path_var, foreground="#0066aa").grid(
            row=4, column=1, columnspan=2, sticky="w", padx=(4, 0), pady=(6, 0)
        )

        self.connect_btn = ttk.Button(form, text="Connect", command=self.on_connect_clicked)
        self.connect_btn.grid(row=4, column=3, sticky="e", pady=(6, 0))

        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(form, textvariable=self.status_var, foreground="#555").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        # --- Results table ---
        results_frame = ttk.Frame(root, padding=(12, 0, 12, 12))
        results_frame.pack(fill="both", expand=True)

        columns = ("status", "filename", "locations")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=16)
        self.tree.heading("status", text="Status")
        self.tree.heading("filename", text="File")
        self.tree.heading("locations", text="Found at (remote path)")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("filename", width=200, anchor="w")
        self.tree.column("locations", width=440, anchor="w")

        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("missing", background="#fde2e2")
        self.tree.tag_configure("duplicate", background="#fff3cd")
        self.tree.tag_configure("ok", background="#e3f6e3")

        self.tree.bind("<Double-1>", self.on_row_double_click)

        ttk.Label(root, text="Tip: double-click a DUPLICATE row to see delete options.",
                  padding=(12, 0, 12, 10), foreground="#777").pack(anchor="w")

        self.last_index = {}  # lowercase_filename -> [remote_paths]
        self._map_photo_cache = None  # cached tk.PhotoImage of the full-res map
        self._map_loading = False

        if paramiko is None:
            messagebox.showerror(
                "Missing dependency",
                "This tool needs the 'paramiko' package.\n\n"
                "Install it first by running:\n"
                "    pip install paramiko --break-system-packages\n\n"
                "then restart this program."
            )
            self.connect_btn.state(["disabled"])

    def open_map_picker_thread(self, on_zone_picked=None):
        if self._map_loading:
            return  # already loading — ignore extra clicks
        if self._map_photo_cache is not None:
            # already cached, just show it immediately, no need to spawn a thread
            self._show_map_window(on_zone_picked)
            return

        self._map_loading = True
        self.map_btn.state(["disabled"])
        self.map_btn.config(text="Loading map…")
        threading.Thread(target=self._load_map_and_open, args=(on_zone_picked,), daemon=True).start()

    def _load_map_and_open(self, on_zone_picked=None):
        try:
            with urllib.request.urlopen(MAP_IMAGE_URL, timeout=15) as resp:
                raw = resp.read()
            b64 = base64.b64encode(raw)
            photo = tk.PhotoImage(data=b64)
            self._map_photo_cache = photo
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "Could not load map",
                f"Failed to download the map image:\n{e}\n\n"
                "Check your internet connection and try again."
            ))
            self.root.after(0, self._reset_map_button)
            return

        self.root.after(0, lambda: self._show_map_window(on_zone_picked))
        self.root.after(0, self._reset_map_button)

    def _reset_map_button(self):
        self._map_loading = False
        self.map_btn.state(["!disabled"])
        self.map_btn.config(text="Pick Zone on Map")

    def _show_map_window(self, on_zone_picked=None):
        photo = self._map_photo_cache
        orig_w, orig_h = photo.width(), photo.height()

        # Scale down to fit a reasonable window (integer subsample factor only)
        max_w = 1800
        factor = max(1, math.ceil(orig_w / max_w))
        display_photo = photo.subsample(factor, factor) if factor > 1 else photo

        win = tk.Toplevel(self.root)
        win.title("Select your zone")
        win.resizable(False, False)

        ttk.Label(win, text="Click your zone on the map", font=("Segoe UI", 11, "bold"),
                  padding=(10, 10, 10, 4)).pack(anchor="w")

        canvas = tk.Canvas(win, width=display_photo.width(), height=display_photo.height(),
                            highlightthickness=0)
        canvas.pack()
        canvas.image = display_photo  # keep a reference alive
        canvas.create_image(0, 0, anchor="nw", image=display_photo)

        def scaled_points(raw_points):
            return [c / factor for c in raw_points]

        polygon_ids = {}
        for zone_name, raw_points in ZONE_SHAPES.items():
            pts = scaled_points(raw_points)
            poly_id = canvas.create_polygon(
                *pts, fill="#35c1e8", outline="#35c1e8", stipple="gray25", width=2
            )
            polygon_ids[poly_id] = zone_name

            # label near the first point of the shape
            canvas.create_text(pts[0] + 4, pts[1] + 4, text=zone_name,
                                anchor="nw", font=("Segoe UI", 7, "bold"),
                                fill="#04141c")

        def on_click(event):
            item = canvas.find_closest(event.x, event.y)
            if not item:
                return
            item_id = item[0]
            zone_name = polygon_ids.get(item_id)
            if zone_name:
                self.zone_var.set(zone_name)
                self._zone_touched = True
                win.destroy()
                if on_zone_picked:
                    on_zone_picked()

        def on_hover(event):
            item = canvas.find_closest(event.x, event.y)
            if item and item[0] in polygon_ids:
                canvas.itemconfig(item[0], fill="#ffffff")
            for pid in polygon_ids:
                if not item or pid != item[0]:
                    canvas.itemconfig(pid, fill="#35c1e8")

        canvas.bind("<Button-1>", on_click)
        canvas.bind("<Motion>", on_hover)

        ttk.Label(win, text="Tip: some zones are small — zoom your screen or click carefully.",
                  foreground="#777", padding=(10, 4, 10, 10)).pack(anchor="w")

    def on_connect_clicked(self):
        if not self._zone_touched:
            # Force them through the map picker first, then continue straight
            # into connecting + browsing for the resources folder.
            self.open_map_picker_thread(on_zone_picked=self.start_connect_thread)
        else:
            self.start_connect_thread()

    def start_connect_thread(self):
        threading.Thread(target=self.connect_and_browse, daemon=True).start()

    def _open_connection(self):
        """Opens a fresh transport/sftp connection using the current form fields."""
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        password = self.pass_var.get()
        port = int(self.port_var.get().strip() or "22")

        transport = paramiko.Transport((host, port))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        return transport, sftp

    def connect_and_browse(self):
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()

        try:
            port = int(self.port_var.get().strip() or "22")
        except ValueError:
            self.status_var.set("Port must be a number.")
            return

        if not host or not user:
            self.status_var.set("Host and username are required.")
            return

        self.status_var.set(f"Connecting to {host}:{port}…")
        self.connect_btn.state(["disabled"])

        try:
            transport, sftp = self._open_connection()
            try:
                start_dir = sftp.normalize(".")
            except Exception:
                start_dir = "/"

            self.status_var.set("Connected. Locate your resources folder…")
            # Open the browser on the main thread
            self.root.after(0, lambda: self.open_folder_browser(sftp, transport, start_dir))

        except Exception as e:
            self.status_var.set(f"Connection failed: {e}")
            messagebox.showerror("Failed", str(e))
            self.connect_btn.state(["!disabled"])

    def open_folder_browser(self, sftp, transport, start_path):
        win = tk.Toplevel(self.root)
        win.title("Locate your resources folder")
        win.geometry("520x460")
        win.transient(self.root)

        ttk.Label(win, text="LOCATE YOUR RESOURCE FOLDER", font=("Segoe UI", 11, "bold"),
                  padding=(12, 12, 12, 4)).pack(anchor="w")

        path_row = ttk.Frame(win)
        path_row.pack(fill="x", padx=12)

        path_var = tk.StringVar(value=start_path)
        ttk.Label(path_row, textvariable=path_var, foreground="#0066aa").pack(side="left", pady=(0, 8))

        def go_up():
            current = path_var.get()
            parent = current.rsplit("/", 1)[0]
            if not parent:
                parent = "/"
            path_var.set(parent)
            list_dirs(parent)

        up_btn = ttk.Button(path_row, text="⬆ Up One Folder", command=lambda: go_up())
        up_btn.pack(side="right")

        listbox = tk.Listbox(win, activestyle="dotbox")
        listbox.pack(fill="both", expand=True, padx=12)

        btn_row = ttk.Frame(win, padding=12)
        btn_row.pack(fill="x")

        status_label = ttk.Label(win, text="", foreground="#a00", padding=(12, 0))
        status_label.pack(anchor="w")

        def list_dirs(path):
            listbox.delete(0, tk.END)
            status_label.config(text="")
            try:
                entries = sftp.listdir_attr(path)
            except Exception as e:
                status_label.config(text=f"Could not read this folder: {e}")
                return
            dirs = sorted(
                [e.filename for e in entries if stat.S_ISDIR(e.st_mode)],
                key=str.lower
            )
            listbox.insert(tk.END, "..")
            for d in dirs:
                listbox.insert(tk.END, d)

        def go_into_selection():
            sel = listbox.curselection()
            if not sel:
                return
            name = listbox.get(sel[0])
            current = path_var.get()
            if name == "..":
                new_path = current.rsplit("/", 1)[0] or "/"
            else:
                new_path = current.rstrip("/") + "/" + name
            path_var.set(new_path)
            list_dirs(new_path)

        def select_this_folder():
            sel = listbox.curselection()
            if sel:
                name = listbox.get(sel[0])
                current = path_var.get()
                if name == "..":
                    chosen = current.rsplit("/", 1)[0] or "/"
                else:
                    chosen = current.rstrip("/") + "/" + name
            else:
                chosen = path_var.get()

            folder_name = chosen.rstrip("/").split("/")[-1]
            if folder_name.lower() != "resources":
                status_label.config(
                    text=f"Please select your \"resources\" folder only. "
                         f"You selected \"{folder_name}\"."
                )
                return
            win.destroy()
            threading.Thread(
                target=self.scan_selected_path, args=(sftp, transport, chosen), daemon=True
            ).start()

        def on_cancel():
            try:
                sftp.close()
                transport.close()
            except Exception:
                pass
            self.connect_btn.state(["!disabled"])
            self.status_var.set("Folder selection cancelled.")
            win.destroy()

        listbox.bind("<Double-Button-1>", lambda e: go_into_selection())

        ttk.Button(btn_row, text="Open folder", command=go_into_selection).pack(side="left")
        ttk.Button(btn_row, text="Select This Folder", command=select_this_folder).pack(side="right")
        ttk.Button(btn_row, text="Cancel", command=on_cancel).pack(side="right", padx=(0, 8))

        win.protocol("WM_DELETE_WINDOW", on_cancel)

        list_dirs(start_path)

    def scan_selected_path(self, sftp, transport, path):
        self.path_var.set(path)
        self.status_var.set(f"Scanning {path}…")

        try:
            t_start = time.time()
            index = try_remote_find(transport, path)
            mode = "fast mode"
            if index is None:
                mode = "fallback mode (parallel)"
                index = sftp_walk_parallel(transport, path, fallback_sftp=sftp)
            elapsed = time.time() - t_start

            self.last_index = index

            sftp.close()
            transport.close()

            self.status_var.set(f"Scan complete in {elapsed:.1f}s ({mode}).")
            self.render_results(index, keep_status=True)

        except Exception as e:
            self.status_var.set(f"Scan failed: {e}")
            messagebox.showerror("Failed", str(e))
        finally:
            self.connect_btn.state(["!disabled"])

    def render_results(self, index, keep_status=False):
        self.tree.delete(*self.tree.get_children())

        selected_zone = self.zone_var.get()
        if selected_zone == ALL_ZONES_LABEL:
            wanted_files = sorted({f for files in ZONES.values() for f in files})
        else:
            wanted_files = ZONES.get(selected_zone, [])

        if not wanted_files:
            self.status_var.set(f"No files configured yet for '{selected_zone}'.")
            return

        missing_count = duplicate_count = ok_count = 0

        for wanted in wanted_files:
            key = wanted.lower()
            paths = index.get(key, [])

            if len(paths) == 0:
                missing_count += 1
                self.tree.insert("", "end", values=("MISSING", wanted, "— not found —"), tags=("missing",))
            elif len(paths) == 1:
                ok_count += 1
                self.tree.insert("", "end", values=("OK", wanted, paths[0]), tags=("ok",))
            else:
                duplicate_count += 1
                locations = "  |  ".join(paths)
                self.tree.insert(
                    "", "end",
                    values=("DUPLICATE", wanted, f"{len(paths)} copies: {locations}"),
                    tags=("duplicate",)
                )

        counts_text = f"OK: {ok_count}   Missing: {missing_count}   Duplicates: {duplicate_count}"
        if keep_status:
            self.status_var.set(f"{self.status_var.get()}   |   {counts_text}")
        else:
            self.status_var.set(counts_text)

    def on_row_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        values = self.tree.item(item[0], "values")
        status, filename = values[0], values[1]
        if status != "DUPLICATE":
            return

        paths = self.last_index.get(filename.lower(), [])
        self.open_delete_dialog(filename, paths)

    def open_delete_dialog(self, filename, paths):
        win = tk.Toplevel(self.root)
        win.title(f"Delete duplicates — {filename}")
        win.geometry("900x560")
        win.minsize(560, 320)

        ttk.Label(win, text=f"Select which copies of '{filename}' to delete:",
                  padding=10, font=("Segoe UI", 11, "bold")).pack(anchor="w")

        # Scrollable list area, in case there are many duplicates
        list_frame = ttk.Frame(win)
        list_frame.pack(fill="both", expand=True, padx=10)

        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Let mouse wheel scroll the canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _cleanup_and_close():
            canvas.unbind_all("<MouseWheel>")
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _cleanup_and_close)

        vars_and_paths = []
        for p in paths:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(inner, text=p, variable=var).pack(anchor="w", pady=3)
            vars_and_paths.append((var, p))

        def do_delete():
            to_delete = [p for v, p in vars_and_paths if v.get()]
            if not to_delete:
                messagebox.showinfo("Nothing selected", "Select at least one file to delete.")
                return
            if len(to_delete) == len(paths):
                if not messagebox.askyesno(
                    "Delete ALL copies?",
                    "You've selected every copy of this file, including what may be "
                    "the correct one. Continue anyway?"
                ):
                    return
            confirm = messagebox.askyesno(
                "Confirm permanent delete",
                "This will permanently delete:\n\n" + "\n".join(to_delete) +
                "\n\nThis cannot be undone. Continue?"
            )
            if not confirm:
                return
            self.delete_remote_files(to_delete)
            _cleanup_and_close()

        btn_row = ttk.Frame(win, padding=14)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Delete Selected", command=do_delete).pack(side="right")
        ttk.Button(btn_row, text="Cancel", command=_cleanup_and_close).pack(side="right", padx=(0, 8))

    def delete_remote_files(self, remote_paths):
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        password = self.pass_var.get()
        try:
            port = int(self.port_var.get().strip() or "22")
        except ValueError:
            port = 22

        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=user, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)

            deleted, failed = [], []
            for p in remote_paths:
                try:
                    sftp.remove(p)
                    deleted.append(p)
                except Exception as e:
                    failed.append((p, str(e)))

            sftp.close()
            transport.close()

            msg = f"Deleted {len(deleted)} file(s)."
            if failed:
                msg += f"\n\nFailed to delete {len(failed)}:\n" + "\n".join(f"{p}: {err}" for p, err in failed)
            messagebox.showinfo("Delete complete", msg)

            # Re-scan the same folder to refresh the view
            try:
                transport2, sftp2 = self._open_connection()
                threading.Thread(
                    target=self.scan_selected_path,
                    args=(sftp2, transport2, self.path_var.get()),
                    daemon=True
                ).start()
            except Exception:
                pass

        except Exception as e:
            messagebox.showerror("Delete failed", str(e))


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = SftpYmapCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()