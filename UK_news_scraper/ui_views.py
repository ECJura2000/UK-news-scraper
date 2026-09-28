from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from functools import partial
from tkinter import ttk
from typing import TYPE_CHECKING

from .config import AGENCIES, DEFAULT_MAX_WORKERS, DEFAULT_OUTPUT_DIR
from .profiles import PARLIAMENT_SOURCE_ID
from .ui_components import COLORS, DateSelector, configure_relevance_tags, english_font_family, font_family

if TYPE_CHECKING:
    from .ui import UKNewsApp


def _configure_styles(self: UKNewsApp) -> None:
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


def _build_shell(self: UKNewsApp) -> None:
    self.sidebar = tk.Frame(self, bg=COLORS["ink"], width=230)
    self.sidebar.pack(side="left", fill="y")
    self.sidebar.pack_propagate(False)
    brand = tk.Canvas(self.sidebar, height=124, bg=COLORS["ink"], highlightthickness=0)
    brand.pack(fill="x")
    brand.create_oval(22, 24, 58, 60, fill=COLORS["core"], outline="")
    brand.create_line(31, 43, 49, 43, fill=COLORS["ink"], width=3)
    brand.create_text(22, 78, anchor="w", text="UK NEWS", fill="white", font=(english_font_family(), 16, "bold"))
    brand.create_text(22, 102, anchor="w", text="RESEARCH DESK", fill="#C9D0DA", font=(english_font_family(), 9))
    for page, label in (
        ("run", "執行抓取"),
        ("profiles", "主題設定"),
        ("results", "篩選結果"),
    ):
        ttk.Button(
            self.sidebar,
            text=label,
            style="Nav.TButton",
            command=partial(self._show_page, page),
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
    self.pages = {}


def _page(self: UKNewsApp, key: str) -> ttk.Frame:
    page = ttk.Frame(self.content, style="Paper.TFrame", padding=30)
    self.pages[key] = page
    return page


def _show_page(self: UKNewsApp, key: str) -> None:
    for page in self.pages.values():
        page.pack_forget()
    self.pages[key].pack(fill="both", expand=True)


def _build_run_page(self: UKNewsApp) -> None:
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


def _build_profile_page(self: UKNewsApp) -> None:
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


def _build_results_page(self: UKNewsApp) -> None:
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
            command=partial(self._sort_results, column),
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
    ttk.Label(detail_frame, textvariable=self.detail_meta_var, style="Surface.TLabel").pack(anchor="w", pady=(8, 12))
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
