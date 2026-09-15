from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser

from .app_service import (
    ExportOptionsRequest,
    ProgressEvent,
    RunCancelled,
    RunRequest,
    RunResult,
    execute_run,
)
from .calendar_utils import CalendarMode, format_date
from .config import AGENCIES, DEFAULT_MAX_WORKERS, DEFAULT_OUTPUT_DIR
from .profiles import (
    DEFAULT_PROFILE_ID,
    PARLIAMENT_SOURCE_ID,
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
    default_profile,
    load_profiles_with_recovery,
    profile_from_dict,
    profile_to_dict,
    restore_default_profiles,
    safe_profile_id,
    save_profiles,
    validate_profile,
)
from .ui_components import (
    COLORS,
    DateSelector,
    configure_relevance_tags,
    enable_high_dpi,
    font_family,
)
from .ui_state import (
    ResultFilters,
    failed_source_ids,
    filter_and_sort_results,
    load_run_history,
)


def launch() -> None:
    enable_high_dpi()
    app = UKNewsApp()
    app.mainloop()


class UKNewsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UK 新聞查詢工作台")
        self.geometry("1440x900")
        self.minsize(1180, 760)
        self.configure(bg=COLORS["paper"])
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._result: RunResult | None = None
        self._result_rows: list[tuple[str, object]] = []
        self._visible_result_rows: list[tuple[str, object]] = []
        self._active_result_item = None
        profile_report = load_profiles_with_recovery()
        self._profiles = profile_report.profiles
        self._profile_warning = profile_report.warning
        self._edit_topics: list[dict[str, object]] = []
        self._source_vars: dict[str, tk.BooleanVar] = {}
        self._cancel_event = threading.Event()
        self._run_thread: threading.Thread | None = None
        self._last_request: RunRequest | None = None
        self._closing = False
        self._history_entries = []
        self._result_sort_column = "score"
        self._result_sort_descending = True
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_styles()
        self._build_shell()
        self._build_profile_page()
        self._build_run_page()
        self._build_results_page()
        self._show_page("run")
        self._load_profile(DEFAULT_PROFILE_ID)
        self._refresh_history()
        if self._profile_warning:
            self.after(
                0,
                lambda: messagebox.showwarning(
                    "設定檔已復原",
                    self._profile_warning,
                ),
            )
        self.after(120, self._poll_queue)

    def _configure_styles(self) -> None:
        scale = max(1.0, self.winfo_fpixels("1i") / 72.0)
        self.tk.call("tk", "scaling", scale)
        family = font_family()
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=(family, 11), background=COLORS["paper"], foreground=COLORS["ink"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Paper.TFrame", background=COLORS["paper"])
        style.configure("Title.TLabel", font=(family, 25, "bold"), background=COLORS["paper"], foreground=COLORS["ink"])
        style.configure("Heading.TLabel", font=(family, 15, "bold"), background=COLORS["surface"], foreground=COLORS["ink"])
        style.configure("Muted.TLabel", background=COLORS["paper"], foreground=COLORS["muted"])
        style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["ink"])
        style.configure("Primary.TButton", padding=(18, 11), background=COLORS["accent"], foreground="white")
        style.map("Primary.TButton", background=[("active", "#276879"), ("disabled", "#A7B0B4")])
        style.configure("Nav.TButton", padding=(16, 14), anchor="w", background=COLORS["ink"], foreground="#F8F2E5")
        style.map("Nav.TButton", background=[("active", COLORS["accent"])])
        style.configure("Treeview", rowheight=32, fieldbackground=COLORS["surface"], background=COLORS["surface"])
        style.configure("Treeview.Heading", font=(family, 10, "bold"), background="#E9E3D5", foreground=COLORS["ink"])
        style.configure("TNotebook", background=COLORS["paper"])
        style.configure("Horizontal.TProgressbar", troughcolor="#E3DDCF", background=COLORS["core"])

    def _build_shell(self) -> None:
        self.sidebar = tk.Frame(self, bg=COLORS["ink"], width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        brand = tk.Canvas(self.sidebar, height=124, bg=COLORS["ink"], highlightthickness=0)
        brand.pack(fill="x")
        brand.create_oval(22, 24, 58, 60, fill=COLORS["core"], outline="")
        brand.create_line(31, 43, 49, 43, fill=COLORS["ink"], width=3)
        brand.create_text(22, 78, anchor="w", text="UK NEWS", fill="white", font=(font_family(), 16, "bold"))
        brand.create_text(22, 102, anchor="w", text="RESEARCH DESK", fill="#C9D0DA", font=(font_family(), 9))
        for page, label in (
            ("run", "執行抓取"),
            ("profiles", "主題設定"),
            ("results", "篩選結果"),
        ):
            ttk.Button(
                self.sidebar,
                text=label,
                style="Nav.TButton",
                command=lambda selected=page: self._show_page(selected),
            ).pack(fill="x", padx=12, pady=4)
        self.scale_var = tk.StringVar(value="100%")
        ttk.Label(self.sidebar, text="介面縮放", background=COLORS["ink"], foreground="#C9D0DA").pack(
            side="bottom", anchor="w", padx=22, pady=(0, 6)
        )
        scale_box = ttk.Combobox(
            self.sidebar,
            textvariable=self.scale_var,
            values=("100%", "125%", "150%", "175%", "200%"),
            state="readonly",
            width=10,
        )
        scale_box.pack(side="bottom", anchor="w", padx=20, pady=(0, 10))
        scale_box.bind("<<ComboboxSelected>>", self._change_scale)
        self.content = ttk.Frame(self, style="Paper.TFrame")
        self.content.pack(side="left", fill="both", expand=True)
        self.pages: dict[str, ttk.Frame] = {}

    def _page(self, key: str) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Paper.TFrame", padding=30)
        self.pages[key] = page
        return page

    def _show_page(self, key: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)

    def _build_run_page(self) -> None:
        page = self._page("run")
        ttk.Label(page, text="執行 UK 新聞查詢", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            page,
            text="選擇期間、主題設定與 Excel 日期格式，完成後直接檢視高相關結果。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(6, 22))
        card = ttk.Frame(page, style="Surface.TFrame", padding=24)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="設定檔", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=8)
        self.run_profile_var = tk.StringVar()
        self.run_profile_box = ttk.Combobox(card, textvariable=self.run_profile_var, state="readonly")
        self.run_profile_box.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(18, 0), pady=8)
        self.run_profile_box.bind("<<ComboboxSelected>>", self._run_profile_selected)

        ttk.Label(card, text="日期紀年", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=8)
        self.ui_calendar_var = tk.StringVar(value="西元")
        calendar_box = ttk.Combobox(
            card,
            textvariable=self.ui_calendar_var,
            values=("西元", "民國"),
            state="readonly",
            width=12,
        )
        calendar_box.grid(row=1, column=1, sticky="w", padx=(18, 20), pady=8)
        calendar_box.bind("<<ComboboxSelected>>", self._calendar_changed)

        today = date.today()
        ttk.Label(card, text="開始日", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=8)
        self.start_selector = DateSelector(card, today - timedelta(days=14))
        self.start_selector.grid(row=2, column=1, sticky="w", padx=(18, 28), pady=8)
        ttk.Label(card, text="結束日", style="Surface.TLabel").grid(row=2, column=2, sticky="w", pady=8)
        self.end_selector = DateSelector(card, today)
        self.end_selector.grid(row=2, column=3, sticky="w", padx=(18, 0), pady=8)

        ttk.Label(card, text="Excel 日期", style="Surface.TLabel").grid(row=3, column=0, sticky="w", pady=8)
        self.excel_calendar_var = tk.StringVar(value="西元 YYYY-MM-DD")
        ttk.Combobox(
            card,
            textvariable=self.excel_calendar_var,
            values=("西元 YYYY-MM-DD", "民國 YYY年MM月DD日"),
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky="w", padx=(18, 28), pady=8)
        ttk.Label(card, text="Worker", style="Surface.TLabel").grid(row=3, column=2, sticky="w", pady=8)
        self.workers_var = tk.IntVar(value=DEFAULT_MAX_WORKERS)
        ttk.Spinbox(card, from_=1, to=16, textvariable=self.workers_var, width=8).grid(
            row=3, column=3, sticky="w", padx=(18, 0), pady=8
        )

        ttk.Label(card, text="輸出資料夾", style="Surface.TLabel").grid(row=4, column=0, sticky="w", pady=8)
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.output_dir_var.trace_add(
            "write",
            lambda *_: self.after_idle(self._refresh_history),
        )
        ttk.Entry(card, textvariable=self.output_dir_var).grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(18, 10), pady=8
        )
        ttk.Button(card, text="選擇", command=self._choose_output_dir).grid(row=4, column=3, sticky="w", pady=8)

        actions = ttk.Frame(page, style="Paper.TFrame")
        actions.pack(fill="x", pady=20)
        self.run_button = ttk.Button(actions, text="開始抓取", style="Primary.TButton", command=self._start_run)
        self.run_button.pack(side="left")
        self.cancel_button = ttk.Button(
            actions,
            text="取消",
            command=self._cancel_run,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(8, 0))
        self.retry_button = ttk.Button(
            actions,
            text="重試異常來源",
            command=self._retry_failed_sources,
            state="disabled",
        )
        self.retry_button.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(actions, maximum=5)
        self.progress.pack(side="left", fill="x", expand=True, padx=18)
        self.run_status_var = tk.StringVar(value="準備就緒")
        ttk.Label(actions, textvariable=self.run_status_var, style="Muted.TLabel").pack(side="right")

        summary = ttk.Frame(page, style="Surface.TFrame", padding=20)
        summary.pack(fill="both", expand=True)
        ttk.Label(summary, text="執行監控與歷史", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))
        notebook = ttk.Notebook(summary)
        notebook.pack(fill="both", expand=True)
        health_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=8)
        history_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=8)
        notebook.add(health_tab, text="來源健康")
        notebook.add(history_tab, text="最近執行")
        self.health_tree = ttk.Treeview(
            health_tab,
            columns=("source", "status", "count", "duration", "warning"),
            show="headings",
            height=10,
        )
        for column, label, width in (
            ("source", "來源", 230),
            ("status", "狀態", 90),
            ("count", "筆數", 70),
            ("duration", "秒數", 70),
            ("warning", "說明", 420),
        ):
            self.health_tree.heading(column, text=label)
            self.health_tree.column(column, width=width, anchor="w")
        self.health_tree.pack(fill="both", expand=True)
        history_actions = ttk.Frame(history_tab, style="Surface.TFrame")
        history_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            history_actions,
            text="重新整理",
            command=self._refresh_history,
        ).pack(side="left")
        ttk.Button(
            history_actions,
            text="開啟 Excel",
            command=self._open_history_workbook,
        ).pack(side="left", padx=6)
        ttk.Button(
            history_actions,
            text="開啟執行摘要",
            command=self._open_history_summary,
        ).pack(side="left")
        self.history_tree = ttk.Treeview(
            history_tab,
            columns=("period", "status", "profile", "news", "filtered", "parliament", "file"),
            show="headings",
            height=7,
        )
        for column, label, width in (
            ("period", "期間", 190),
            ("status", "狀態", 85),
            ("profile", "設定檔", 160),
            ("news", "新聞", 60),
            ("filtered", "初篩", 60),
            ("parliament", "國會", 60),
            ("file", "檔案", 280),
        ):
            self.history_tree.heading(column, text=label)
            self.history_tree.column(column, width=width, anchor="w")
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind(
            "<Double-1>",
            lambda _event: self._open_history_workbook(),
        )

    def _build_profile_page(self) -> None:
        page = self._page("profiles")
        ttk.Label(page, text="主題與關鍵詞設定", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            page,
            text="建立可重用的查詢設定；核心、一般、輔助詞分別使用深、中、淺黃色。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(6, 18))
        toolbar = ttk.Frame(page, style="Paper.TFrame")
        toolbar.pack(fill="x", pady=(0, 12))
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(toolbar, textvariable=self.profile_var, state="readonly", width=34)
        self.profile_box.pack(side="left")
        self.profile_box.bind("<<ComboboxSelected>>", self._profile_selected)
        for label, command in (
            ("新增", self._new_profile),
            ("複製", self._duplicate_profile),
            ("保存", self._save_profile),
            ("還原內建", self._restore_profiles),
            ("刪除", self._delete_profile),
            ("匯入", self._import_profile),
            ("匯出", self._export_profile),
        ):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(8, 0))

        form = ttk.Frame(page, style="Surface.TFrame", padding=18)
        form.pack(fill="x")
        self.profile_name_var = tk.StringVar()
        self.profile_id_var = tk.StringVar()
        self.threshold_var = tk.IntVar(value=3)
        ttk.Label(form, text="名稱", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.profile_name_var, width=30).grid(row=0, column=1, padx=8)
        ttk.Label(form, text="ID", style="Surface.TLabel").grid(row=0, column=2, sticky="w", padx=(18, 0))
        ttk.Entry(form, textvariable=self.profile_id_var, width=24).grid(row=0, column=3, padx=8)
        ttk.Label(form, text="最低分數", style="Surface.TLabel").grid(row=0, column=4, sticky="w", padx=(18, 0))
        ttk.Spinbox(form, from_=1, to=999, textvariable=self.threshold_var, width=8).grid(row=0, column=5, padx=8)

        body = ttk.Panedwindow(page, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(14, 0))
        sources = ttk.Frame(body, style="Surface.TFrame", padding=15)
        topics = ttk.Frame(body, style="Surface.TFrame", padding=15)
        keywords = ttk.Frame(body, style="Surface.TFrame", padding=15)
        body.add(sources, weight=1)
        body.add(topics, weight=1)
        body.add(keywords, weight=2)
        ttk.Label(sources, text="資料來源", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        for source_id, label in [
            *((agency.short_name, agency.display_name) for agency in AGENCIES),
            (PARLIAMENT_SOURCE_ID, "UK Parliament 研究資料"),
        ]:
            variable = tk.BooleanVar(value=True)
            self._source_vars[source_id] = variable
            ttk.Checkbutton(sources, text=label, variable=variable).pack(anchor="w", pady=2)

        topic_header = ttk.Frame(topics, style="Surface.TFrame")
        topic_header.pack(fill="x")
        ttk.Label(topic_header, text="主題", style="Heading.TLabel").pack(side="left")
        ttk.Button(topic_header, text="+", width=3, command=self._add_topic).pack(side="right")
        ttk.Button(topic_header, text="−", width=3, command=self._delete_topic).pack(side="right", padx=4)
        self.topic_tree = ttk.Treeview(topics, columns=("name",), show="headings", height=14)
        self.topic_tree.heading("name", text="主題名稱")
        self.topic_tree.column("name", width=220)
        self.topic_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.topic_tree.bind("<<TreeviewSelect>>", self._topic_selected)
        self.topic_tree.bind("<Double-1>", self._rename_topic)

        keyword_header = ttk.Frame(keywords, style="Surface.TFrame")
        keyword_header.pack(fill="x")
        ttk.Label(keyword_header, text="關鍵詞", style="Heading.TLabel").pack(side="left")
        ttk.Button(keyword_header, text="新增", command=self._add_keyword).pack(side="right")
        ttk.Button(keyword_header, text="刪除", command=self._delete_keyword).pack(side="right", padx=4)
        self.keyword_tree = ttk.Treeview(
            keywords,
            columns=("phrase", "strength", "title", "summary"),
            show="headings",
            height=14,
        )
        for column, label, width in (
            ("phrase", "詞組", 270),
            ("strength", "強度", 80),
            ("title", "標題分", 70),
            ("summary", "摘要分", 70),
        ):
            self.keyword_tree.heading(column, text=label)
            self.keyword_tree.column(column, width=width)
        self.keyword_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.keyword_tree.bind("<Double-1>", self._edit_keyword)

    def _build_results_page(self) -> None:
        page = self._page("results")
        ttk.Label(page, text="篩選結果", style="Title.TLabel").pack(anchor="w")
        filters = ttk.Frame(page, style="Paper.TFrame")
        filters.pack(fill="x", pady=(12, 14))
        filters_top = ttk.Frame(filters, style="Paper.TFrame")
        filters_top.pack(fill="x")
        filters_bottom = ttk.Frame(filters, style="Paper.TFrame")
        filters_bottom.pack(fill="x", pady=(8, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_results())
        ttk.Entry(filters_top, textvariable=self.search_var, width=34).pack(side="left")
        self.result_type_var = tk.StringVar(value="全部")
        type_box = ttk.Combobox(
            filters_top,
            textvariable=self.result_type_var,
            values=("全部", "新聞", "國會研究"),
            state="readonly",
            width=12,
        )
        type_box.pack(side="left", padx=8)
        type_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_results())
        self.result_strength_var = tk.StringVar(value="全部強度")
        strength_box = ttk.Combobox(
            filters_top,
            textvariable=self.result_strength_var,
            values=("全部強度", "核心", "一般", "輔助"),
            state="readonly",
            width=12,
        )
        strength_box.pack(side="left")
        strength_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_results())
        self.result_source_var = tk.StringVar(value="全部來源")
        self.result_source_box = ttk.Combobox(
            filters_top,
            textvariable=self.result_source_var,
            values=("全部來源",),
            state="readonly",
            width=18,
        )
        self.result_source_box.pack(side="left", padx=8)
        self.result_source_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_results())
        self.result_topic_var = tk.StringVar(value="全部主題")
        self.result_topic_box = ttk.Combobox(
            filters_top,
            textvariable=self.result_topic_var,
            values=("全部主題",),
            state="readonly",
            width=18,
        )
        self.result_topic_box.pack(side="left")
        self.result_topic_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_results())
        ttk.Button(filters_top, text="開啟 Excel", command=self._open_workbook).pack(side="right")

        ttk.Label(filters_bottom, text="分數").pack(side="left")
        self.result_min_score_var = tk.IntVar(value=0)
        minimum_score = ttk.Spinbox(
            filters_bottom,
            from_=0,
            to=999,
            textvariable=self.result_min_score_var,
            width=5,
            command=self._refresh_results,
        )
        minimum_score.pack(side="left", padx=(6, 2))
        minimum_score.bind("<KeyRelease>", lambda _event: self._refresh_results())
        ttk.Label(filters_bottom, text="至").pack(side="left")
        self.result_max_score_var = tk.IntVar(value=999)
        maximum_score = ttk.Spinbox(
            filters_bottom,
            from_=0,
            to=999,
            textvariable=self.result_max_score_var,
            width=5,
            command=self._refresh_results,
        )
        maximum_score.pack(side="left", padx=6)
        maximum_score.bind("<KeyRelease>", lambda _event: self._refresh_results())
        self.result_date_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filters_bottom,
            text="日期",
            variable=self.result_date_enabled_var,
            command=self._refresh_results,
        ).pack(side="left", padx=(14, 6))
        today = date.today()
        self.result_start_selector = DateSelector(
            filters_bottom,
            today - timedelta(days=14),
            self._refresh_results,
        )
        self.result_start_selector.pack(side="left")
        ttk.Label(filters_bottom, text="至").pack(side="left", padx=6)
        self.result_end_selector = DateSelector(
            filters_bottom,
            today,
            self._refresh_results,
        )
        self.result_end_selector.pack(side="left")
        ttk.Button(
            filters_bottom,
            text="清除篩選",
            command=self._clear_result_filters,
        ).pack(side="left", padx=12)
        self.result_count_var = tk.StringVar(value="顯示 0 筆")
        ttk.Label(
            filters_bottom,
            textvariable=self.result_count_var,
            style="Muted.TLabel",
        ).pack(side="right")

        pane = ttk.Panedwindow(page, orient="horizontal")
        pane.pack(fill="both", expand=True)
        list_frame = ttk.Frame(pane, style="Surface.TFrame", padding=12)
        detail_frame = ttk.Frame(pane, style="Surface.TFrame", padding=18)
        pane.add(list_frame, weight=3)
        pane.add(detail_frame, weight=2)
        self.result_tree = ttk.Treeview(
            list_frame,
            columns=("type", "date", "source", "score", "level", "title"),
            show="headings",
        )
        for column, label, width in (
            ("type", "類型", 80),
            ("date", "日期", 100),
            ("source", "來源", 160),
            ("score", "分數", 60),
            ("level", "可能性", 70),
            ("title", "標題", 500),
        ):
            self.result_tree.heading(
                column,
                text=label,
                command=lambda selected=column: self._sort_results(selected),
            )
            self.result_tree.column(column, width=width)
        self.result_tree.pack(fill="both", expand=True)
        self.result_tree.bind("<<TreeviewSelect>>", self._result_selected)

        self.detail_title_var = tk.StringVar(value="尚無結果")
        ttk.Label(
            detail_frame,
            textvariable=self.detail_title_var,
            style="Heading.TLabel",
            wraplength=420,
        ).pack(anchor="w")
        self.detail_meta_var = tk.StringVar()
        ttk.Label(detail_frame, textvariable=self.detail_meta_var, style="Surface.TLabel").pack(
            anchor="w", pady=(8, 12)
        )
        self.detail_text = tk.Text(
            detail_frame,
            wrap="word",
            relief="flat",
            bg=COLORS["surface"],
            fg=COLORS["ink"],
            font=(font_family(), 11),
            padx=4,
            pady=4,
        )
        self.detail_text.pack(fill="both", expand=True)
        configure_relevance_tags(self.detail_text)
        self.detail_text.configure(state="disabled")
        ttk.Button(detail_frame, text="開啟原始資料", command=self._open_source).pack(anchor="e", pady=(12, 0))

    def _change_scale(self, _event=None) -> None:
        factor = int(self.scale_var.get().replace("%", "")) / 100
        base = max(1.0, self.winfo_fpixels("1i") / 72.0)
        self.tk.call("tk", "scaling", base * factor)

    def _profile_labels(self) -> tuple[list[str], dict[str, str]]:
        labels = [f"{profile.name}  [{profile.profile_id}]" for profile in self._profiles.values()]
        mapping = {
            f"{profile.name}  [{profile.profile_id}]": profile.profile_id
            for profile in self._profiles.values()
        }
        return labels, mapping

    def _refresh_profile_boxes(self, selected_id: str) -> None:
        labels, mapping = self._profile_labels()
        self._profile_label_to_id = mapping
        self.profile_box["values"] = labels
        self.run_profile_box["values"] = labels
        selected_label = next(label for label, profile_id in mapping.items() if profile_id == selected_id)
        self.profile_var.set(selected_label)
        self.run_profile_var.set(selected_label)

    def _load_profile(self, profile_id: str) -> None:
        profile = self._profiles[profile_id]
        self._refresh_profile_boxes(profile_id)
        self.profile_name_var.set(profile.name)
        self.profile_id_var.set(profile.profile_id)
        self.threshold_var.set(profile.minimum_score)
        for source_id, variable in self._source_vars.items():
            variable.set(source_id in profile.selected_sources)
        self._edit_topics = [
            {
                "name": topic.name,
                "keywords": [
                    {"phrase": keyword.phrase, "strength": keyword.strength}
                    for keyword in topic.keywords
                ],
            }
            for topic in profile.topics
        ]
        self._refresh_topics()

    def _profile_selected(self, _event=None) -> None:
        self._load_profile(self._profile_label_to_id[self.profile_var.get()])

    def _run_profile_selected(self, _event=None) -> None:
        selected_id = self._profile_label_to_id[self.run_profile_var.get()]
        self.profile_var.set(self.run_profile_var.get())
        self._load_profile(selected_id)

    def _profile_from_form(self) -> FilterProfile:
        topics = tuple(
            ProfileTopic(
                name=str(topic["name"]),
                keywords=tuple(
                    KeywordDefinition(
                        phrase=str(keyword["phrase"]),
                        strength=keyword["strength"],
                    )
                    for keyword in topic["keywords"]
                ),
            )
            for topic in self._edit_topics
        )
        return validate_profile(
            FilterProfile(
                profile_id=safe_profile_id(self.profile_id_var.get()),
                name=self.profile_name_var.get().strip(),
                description="由 UK 新聞查詢工作台建立",
                version=1,
                selected_sources=tuple(
                    source_id for source_id, variable in self._source_vars.items() if variable.get()
                ),
                topics=topics,
                minimum_score=int(self.threshold_var.get()),
            )
        )

    def _save_profile(self) -> None:
        try:
            profile = self._profile_from_form()
            if profile.is_default:
                raise ValueError("內建設定檔不可覆寫；請先使用「複製」建立自訂設定")
            self._profiles[profile.profile_id] = profile
            save_profiles(list(self._profiles.values()))
            self._refresh_profile_boxes(profile.profile_id)
            messagebox.showinfo("設定已保存", f"已保存「{profile.name}」。")
        except (ValueError, OSError) as exc:
            messagebox.showerror("無法保存", str(exc))

    def _restore_profiles(self) -> None:
        if not messagebox.askyesno(
            "還原內建設定",
            "確定移除所有自訂設定並還原內建科技法制設定？目前設定會保留備份。",
        ):
            return
        try:
            self._profiles = restore_default_profiles()
            self._load_profile(DEFAULT_PROFILE_ID)
        except OSError as exc:
            messagebox.showerror("無法還原", str(exc))
            return
        messagebox.showinfo("設定已還原", "已還原內建科技法制設定。")

    def _new_profile(self) -> None:
        name = simpledialog.askstring("新增設定檔", "設定檔名稱：", parent=self)
        if not name:
            return
        profile_id = safe_profile_id(name)
        suffix = 2
        while profile_id in self._profiles:
            profile_id = f"{safe_profile_id(name)}-{suffix}"
            suffix += 1
        template = replace(default_profile(), profile_id=profile_id, name=name)
        self._profiles[profile_id] = template
        self._load_profile(profile_id)

    def _duplicate_profile(self) -> None:
        source = self._profile_from_form()
        name = simpledialog.askstring("複製設定檔", "新設定檔名稱：", initialvalue=f"{source.name} 副本", parent=self)
        if not name:
            return
        profile_id = safe_profile_id(name)
        suffix = 2
        while profile_id in self._profiles:
            profile_id = f"{safe_profile_id(name)}-{suffix}"
            suffix += 1
        duplicated = replace(source, profile_id=profile_id, name=name)
        self._profiles[profile_id] = duplicated
        self._load_profile(profile_id)

    def _delete_profile(self) -> None:
        profile_id = safe_profile_id(self.profile_id_var.get())
        if profile_id == DEFAULT_PROFILE_ID:
            messagebox.showwarning("無法刪除", "內建設定檔不可刪除。")
            return
        if not messagebox.askyesno("刪除設定檔", f"確定刪除「{self.profile_name_var.get()}」？"):
            return
        self._profiles.pop(profile_id, None)
        save_profiles(list(self._profiles.values()))
        self._load_profile(DEFAULT_PROFILE_ID)

    def _import_profile(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            profile = profile_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
            if profile.profile_id == DEFAULT_PROFILE_ID:
                profile = replace(profile, profile_id=f"{DEFAULT_PROFILE_ID}-imported")
            if profile.profile_id in self._profiles and not messagebox.askyesno(
                "設定檔已存在",
                f"設定檔 ID「{profile.profile_id}」已存在，是否覆寫？",
            ):
                return
            self._profiles[profile.profile_id] = profile
            save_profiles(list(self._profiles.values()))
            self._load_profile(profile.profile_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("匯入失敗", str(exc))

    def _export_profile(self) -> None:
        try:
            profile = self._profile_from_form()
        except ValueError as exc:
            messagebox.showerror("設定無效", str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"{profile.profile_id}.json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            Path(path).write_text(
                json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def _refresh_topics(self) -> None:
        self.topic_tree.delete(*self.topic_tree.get_children())
        for index, topic in enumerate(self._edit_topics):
            self.topic_tree.insert("", "end", iid=str(index), values=(topic["name"],))
        if self._edit_topics:
            self.topic_tree.selection_set("0")
            self._refresh_keywords(0)
        else:
            self.keyword_tree.delete(*self.keyword_tree.get_children())

    def _selected_topic_index(self) -> int | None:
        selection = self.topic_tree.selection()
        return int(selection[0]) if selection else None

    def _topic_selected(self, _event=None) -> None:
        index = self._selected_topic_index()
        if index is not None:
            self._refresh_keywords(index)

    def _refresh_keywords(self, topic_index: int) -> None:
        self.keyword_tree.delete(*self.keyword_tree.get_children())
        weights = {
            KeywordStrength.CORE: (6, 4),
            KeywordStrength.GENERAL: (4, 3),
            KeywordStrength.SUPPORTING: (2, 1),
        }
        for index, keyword in enumerate(self._edit_topics[topic_index]["keywords"]):
            strength = keyword["strength"]
            title_score, summary_score = weights[strength]
            self.keyword_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(keyword["phrase"], strength.label, title_score, summary_score),
                tags=(strength.value,),
            )
        self.keyword_tree.tag_configure("core", background=COLORS["core"])
        self.keyword_tree.tag_configure("general", background=COLORS["general"])
        self.keyword_tree.tag_configure("supporting", background=COLORS["supporting"])

    def _add_topic(self) -> None:
        name = simpledialog.askstring("新增主題", "主題名稱：", parent=self)
        if name:
            self._edit_topics.append({"name": name.strip(), "keywords": []})
            self._refresh_topics()
            item_id = str(len(self._edit_topics) - 1)
            self.topic_tree.selection_set(item_id)
            self.topic_tree.see(item_id)

    def _delete_topic(self) -> None:
        index = self._selected_topic_index()
        if index is not None:
            self._edit_topics.pop(index)
            self._refresh_topics()

    def _rename_topic(self, _event=None) -> None:
        index = self._selected_topic_index()
        if index is None:
            return
        current = str(self._edit_topics[index]["name"])
        name = simpledialog.askstring("編輯主題", "主題名稱：", initialvalue=current, parent=self)
        if name:
            self._edit_topics[index]["name"] = name.strip()
            self._refresh_topics()

    def _add_keyword(self) -> None:
        topic_index = self._selected_topic_index()
        if topic_index is None:
            messagebox.showwarning("請先選擇主題", "新增關鍵詞前請先建立或選擇主題。")
            return
        phrase = simpledialog.askstring("新增關鍵詞", "關鍵詞或詞組：", parent=self)
        if not phrase:
            return
        strength = self._ask_strength()
        if strength:
            self._edit_topics[topic_index]["keywords"].append(
                {"phrase": phrase.strip(), "strength": strength}
            )
            self._refresh_keywords(topic_index)

    def _edit_keyword(self, _event=None) -> None:
        topic_index = self._selected_topic_index()
        selection = self.keyword_tree.selection()
        if topic_index is None or not selection:
            return
        keyword_index = int(selection[0])
        keyword = self._edit_topics[topic_index]["keywords"][keyword_index]
        phrase = simpledialog.askstring(
            "編輯關鍵詞",
            "關鍵詞或詞組：",
            initialvalue=str(keyword["phrase"]),
            parent=self,
        )
        if not phrase:
            return
        strength = self._ask_strength(keyword["strength"])
        if strength:
            keyword["phrase"] = phrase.strip()
            keyword["strength"] = strength
            self._refresh_keywords(topic_index)

    def _ask_strength(self, initial: KeywordStrength = KeywordStrength.GENERAL):
        value = simpledialog.askstring(
            "關鍵詞強度",
            "輸入：核心、一般或輔助",
            initialvalue=initial.label,
            parent=self,
        )
        mapping = {"核心": KeywordStrength.CORE, "一般": KeywordStrength.GENERAL, "輔助": KeywordStrength.SUPPORTING}
        if value not in mapping:
            if value is not None:
                messagebox.showerror("強度無效", "請輸入核心、一般或輔助。")
            return None
        return mapping[value]

    def _delete_keyword(self) -> None:
        topic_index = self._selected_topic_index()
        selection = self.keyword_tree.selection()
        if topic_index is not None and selection:
            self._edit_topics[topic_index]["keywords"].pop(int(selection[0]))
            self._refresh_keywords(topic_index)

    def _calendar_changed(self, _event=None) -> None:
        mode = CalendarMode.ROC if self.ui_calendar_var.get() == "民國" else CalendarMode.GREGORIAN
        self.start_selector.set_mode(mode)
        self.end_selector.set_mode(mode)
        self.result_start_selector.set_mode(mode)
        self.result_end_selector.set_mode(mode)
        self._refresh_results()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if selected:
            self.output_dir_var.set(selected)

    def _start_run(self) -> None:
        try:
            period_start = self.start_selector.get()
            period_end = self.end_selector.get()
            if period_end < period_start:
                raise ValueError("結束日期不得早於開始日期")
            profile_id = self._profile_label_to_id[self.run_profile_var.get()]
            profile = self._profiles[profile_id]
            output_dir = Path(self.output_dir_var.get()).expanduser()
            if not output_dir:
                raise ValueError("請選擇輸出資料夾")
            calendar_mode = (
                CalendarMode.ROC
                if self.excel_calendar_var.get().startswith("民國")
                else CalendarMode.GREGORIAN
            )
            request = RunRequest(
                period_start=period_start,
                period_end=period_end,
                output_dir=output_dir,
                workers=int(self.workers_var.get()),
                profile=profile,
                export_options=ExportOptionsRequest(calendar_mode=calendar_mode),
            )
        except (ValueError, KeyError) as exc:
            messagebox.showerror("無法執行", str(exc))
            return
        self._launch_run(request)

    def _launch_run(self, request: RunRequest) -> None:
        if self._run_thread and self._run_thread.is_alive():
            messagebox.showwarning("已有執行中工作", "請等待目前工作完成或先取消。")
            return
        self._last_request = request
        self._cancel_event.clear()
        self.run_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress["value"] = 0
        self.run_status_var.set("正在啟動…")
        self.health_tree.delete(*self.health_tree.get_children())
        self._run_thread = threading.Thread(
            target=self._run_worker,
            args=(request,),
            daemon=False,
        )
        self._run_thread.start()

    def _cancel_run(self) -> None:
        if not self._run_thread or not self._run_thread.is_alive():
            return
        self._cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.run_status_var.set("正在安全取消；目前下載完成後停止…")

    def _retry_failed_sources(self) -> None:
        if not self._result or not self._last_request:
            messagebox.showinfo("沒有可重試工作", "請先完成一次抓取。")
            return
        source_ids = failed_source_ids(self._result.summary.source_health)
        if not source_ids:
            messagebox.showinfo("來源皆正常", "目前沒有異常來源需要重試。")
            return
        request = replace(
            self._last_request,
            retry_source_ids=source_ids,
            base_result=self._result,
        )
        self._launch_run(request)

    def _run_worker(self, request: RunRequest) -> None:
        try:
            result = execute_run(
                request,
                progress=lambda event: self._queue.put(("progress", event)),
                cancelled=self._cancel_event.is_set,
            )
        except RunCancelled as exc:
            self._queue.put(("cancelled", exc))
        except Exception as exc:
            self._queue.put(("error", exc))
        else:
            self._queue.put(("result", result))

    def _poll_queue(self) -> None:
        terminal_event = False
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    self._handle_progress(payload)
                elif kind == "result":
                    self._handle_result(payload)
                    terminal_event = True
                elif kind == "cancelled":
                    self._finish_run_controls()
                    self.run_status_var.set("執行已取消")
                    terminal_event = True
                elif kind == "error":
                    self._finish_run_controls()
                    self.run_status_var.set("執行失敗")
                    if not self._closing:
                        messagebox.showerror("執行失敗", str(payload))
                    terminal_event = True
        except queue.Empty:
            pass
        if self._closing and terminal_event:
            self.destroy()
            return
        self.after(120, self._poll_queue)

    def _finish_run_controls(self) -> None:
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        can_retry = bool(
            self._result
            and failed_source_ids(self._result.summary.source_health)
        )
        self.retry_button.configure(state="normal" if can_retry else "disabled")

    def _handle_progress(self, event: ProgressEvent) -> None:
        self.progress["maximum"] = event.total or 5
        self.progress["value"] = event.current
        self.run_status_var.set(event.message)

    def _handle_result(self, result: RunResult) -> None:
        self._result = result
        self._finish_run_controls()
        self.run_status_var.set(
            f"完成：新聞 {result.summary.all_news_count}，初篩 {result.summary.filtered_news_count}，"
            f"國會 {result.summary.parliament_count}"
        )
        for health in result.summary.source_health:
            self.health_tree.insert(
                "",
                "end",
                values=(
                    health.source,
                    "正常" if health.success and not health.warning else "注意",
                    health.item_count,
                    health.duration_seconds,
                    health.warning,
                ),
            )
        self._result_rows = [
            *(("新聞", item) for item in result.filtered_items),
            *(("國會研究", item) for item in result.filtered_parliament_items),
        ]
        sources = sorted(
            {
                item.agency if item_type == "新聞" else item.publisher
                for item_type, item in self._result_rows
            }
        )
        topics = sorted(
            {
                topic
                for _item_type, item in self._result_rows
                for topic in item.matched_topics
            }
        )
        self.result_source_box["values"] = ("全部來源", *sources)
        self.result_topic_box["values"] = ("全部主題", *topics)
        self.result_source_var.set("全部來源")
        self.result_topic_var.set("全部主題")
        self.result_date_enabled_var.set(False)
        self.result_start_selector.set(date.fromisoformat(result.summary.period_start))
        self.result_end_selector.set(date.fromisoformat(result.summary.period_end))
        self._refresh_results()
        self._refresh_history()
        self._show_page("results")

    def _refresh_results(self) -> None:
        if not hasattr(self, "result_tree"):
            return
        self.result_tree.delete(*self.result_tree.get_children())
        try:
            minimum_score = int(self.result_min_score_var.get())
            maximum_score = int(self.result_max_score_var.get())
        except (ValueError, tk.TclError):
            self.result_count_var.set("分數格式無效")
            return
        if minimum_score > maximum_score:
            self.result_count_var.set("最低分不得高於最高分")
            return
        use_dates = self.result_date_enabled_var.get()
        filters = ResultFilters(
            query=self.search_var.get(),
            item_type=self.result_type_var.get(),
            strength=self.result_strength_var.get(),
            source=self.result_source_var.get(),
            topic=self.result_topic_var.get(),
            minimum_score=minimum_score,
            maximum_score=maximum_score,
            date_start=self.result_start_selector.get() if use_dates else None,
            date_end=self.result_end_selector.get() if use_dates else None,
        )
        self._visible_result_rows = filter_and_sort_results(
            self._result_rows,
            filters,
            sort_column=self._result_sort_column,
            descending=self._result_sort_descending,
        )
        calendar_mode = (
            CalendarMode.ROC
            if self.ui_calendar_var.get() == "民國"
            else CalendarMode.GREGORIAN
        )
        for index, (item_type, item) in enumerate(self._visible_result_rows):
            source = item.agency if item_type == "新聞" else item.publisher
            self.result_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item_type,
                    format_date(item.published_at.date(), calendar_mode),
                    source,
                    item.relevance_score,
                    item.relevance_level,
                    item.title,
                ),
            )
        self.result_count_var.set(
            f"顯示 {len(self._visible_result_rows)}／{len(self._result_rows)} 筆"
        )

    def _sort_results(self, column: str) -> None:
        if self._result_sort_column == column:
            self._result_sort_descending = not self._result_sort_descending
        else:
            self._result_sort_column = column
            self._result_sort_descending = column in {"date", "score", "level"}
        self._refresh_results()

    def _clear_result_filters(self) -> None:
        self.search_var.set("")
        self.result_type_var.set("全部")
        self.result_strength_var.set("全部強度")
        self.result_source_var.set("全部來源")
        self.result_topic_var.set("全部主題")
        self.result_min_score_var.set(0)
        self.result_max_score_var.set(999)
        self.result_date_enabled_var.set(False)
        self._result_sort_column = "score"
        self._result_sort_descending = True
        self._refresh_results()

    def _result_selected(self, _event=None) -> None:
        selection = self.result_tree.selection()
        if not selection:
            return
        item_type, item = self._visible_result_rows[int(selection[0])]
        self._active_result_item = item
        calendar_mode = (
            CalendarMode.ROC
            if self.ui_calendar_var.get() == "民國"
            else CalendarMode.GREGORIAN
        )
        self.detail_title_var.set(item.title)
        self.detail_meta_var.set(
            f"{item_type}｜{format_date(item.published_at.date(), calendar_mode)}｜"
            f"{item.relevance_level}可能性｜{item.relevance_score} 分\n"
            f"主題：{'、'.join(item.matched_topics)}"
        )
        content = f"{item.title}\n\n{item.summary or '（無摘要）'}"
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", content)
        strengths = {
            **item.summary_keyword_strengths,
            **item.title_keyword_strengths,
        }
        strength_order = {"supporting": 0, "general": 1, "core": 2}
        for keyword, strength in sorted(
            strengths.items(),
            key=lambda entry: strength_order[entry[1]],
        ):
            start = "1.0"
            while True:
                position = self.detail_text.search(keyword, start, stopindex="end", nocase=True)
                if not position:
                    break
                end = f"{position}+{len(keyword)}c"
                self.detail_text.tag_add(strength, position, end)
                start = end
        self.detail_text.configure(state="disabled")

    def _open_source(self) -> None:
        if not self._active_result_item:
            return
        url = getattr(self._active_result_item, "link", "") or getattr(
            self._active_result_item,
            "webpage_url",
            "",
        )
        if url:
            webbrowser.open(url)

    def _open_workbook(self) -> None:
        if not self._result:
            messagebox.showinfo("尚無結果", "請先完成一次抓取。")
            return
        self._open_path(self._result.workbook_path)

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_tree"):
            return
        self._history_entries = load_run_history(self.output_dir_var.get())
        self.history_tree.delete(*self.history_tree.get_children())
        for index, entry in enumerate(self._history_entries):
            self.history_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{entry.period_start.isoformat()} ～ {entry.period_end.isoformat()}",
                    entry.status,
                    entry.profile_name,
                    entry.all_news_count,
                    entry.filtered_news_count,
                    entry.parliament_count,
                    entry.workbook_path.name,
                ),
            )

    def _selected_history_entry(self):
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showinfo("請選擇紀錄", "請先選擇一筆最近執行紀錄。")
            return None
        return self._history_entries[int(selection[0])]

    def _open_history_workbook(self) -> None:
        entry = self._selected_history_entry()
        if entry:
            self._open_path(entry.workbook_path)

    def _open_history_summary(self) -> None:
        entry = self._selected_history_entry()
        if entry:
            self._open_path(entry.summary_path)

    def _open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("檔案不存在", f"找不到檔案：{path}")
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _on_close(self) -> None:
        if self._run_thread and self._run_thread.is_alive():
            if not messagebox.askyesno(
                "工作仍在執行",
                "要取消目前工作並在安全停止後關閉嗎？",
            ):
                return
            self._closing = True
            self._cancel_run()
            self.run_button.configure(state="disabled")
            self.retry_button.configure(state="disabled")
            return
        self.destroy()


if __name__ == "__main__":
    launch()
