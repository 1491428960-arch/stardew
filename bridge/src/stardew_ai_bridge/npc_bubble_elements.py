"""群聊回放页的好感度角色视觉元素，不承载角色声线或 persona。

色板与备用标志物遵循 docs/npc-bubble-elements-2026-09-19.json。
motifs[0] 是 24×24 画布的像素道具，页面只需包一层 SVG；其余两项留作标志物库。
ornament 是环绕框架及 32×32 固有色物件，所有路径沿整数像素绘制。
"""

from __future__ import annotations

from .npc_bubble_catalog import NPC_BUBBLE_ALIASES, NPC_CATALOG, OBJECT_CATALOG
from .npc_bubble_objects import OBJECT_SVGS


def canonical_npc_id(npc_id: str) -> str:
    """Resolve known save IDs while leaving unknown display IDs unchanged."""
    return NPC_BUBBLE_ALIASES.get(npc_id, npc_id)


NPC_BUBBLE_ELEMENTS = {
    "Abigail": {
        "icon": '✦',
        "tone": NPC_CATALOG["Abigail"]["tone"],
        "palette": dict(NPC_CATALOG["Abigail"]["palette"]),
        "ornament": {
            "label": "紫水晶与小剑",
            "kind": "crystal",
            "colors": {"line": "#7656a4", "highlight": "#c3a0ed", "leaf": "#8e73bd", "leafHi": "#d6b7f2"},
            "objects": (
                (
                    '<path fill="#20202c" d="M14 2H18V4H21V10H24V8H27V12H30V24H28V28H23V30H8V28H4V24H2V14H5V11H9V15H11V7H14Z"/>'
                    '<path fill="#654196" d="M14 6H19V24H23V28H10V26H6V23H4V15H7V13H8V18H13V8H14Z"/>'
                    '<path fill="#a674d4" d="M15 4H17V6H19V22H17V26H13V22H12V9H15ZM24 12H26V14H28V23H26V26H22V18H24Z"/>'
                    '<path fill="#d6b6f1" d="M15 6H17V17H15V22H13V10H15ZM24 14H26V21H24ZM5 16H7V22H5Z"/>'
                    '<path fill="#462d70" d="M17 22H19V26H17ZM8 20H10V25H8ZM26 23H28V26H26Z"/>'
                    '<rect fill="#f3dfff" x="15" y="6" width="2" height="5"/>'
                ),
                (
                    '<path fill="#20202c" d="M14 2H18V4H20V19H26V23H21V25H19V28H20V30H12V28H13V25H11V23H6V19H12V4H14Z"/>'
                    '<path fill="#aebcd3" d="M14 6H16V4H17V6H18V19H14Z"/>'
                    '<path fill="#edf3f4" d="M14 7H16V18H14Z"/>'
                    '<rect fill="#7888a6" x="16" y="9" width="2" height="10"/>'
                    '<path fill="#b38be0" d="M8 20H24V22H19V24H13V22H8Z"/>'
                    '<rect fill="#634582" x="15" y="24" width="2" height="4"/>'
                    '<rect fill="#e0b4f4" x="14" y="28" width="4" height="1"/>'
                    '<rect fill="#e9c67d" x="14" y="20" width="4" height="2"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M10 1H14V3H16V5H18V9H20V13H18V17H16V20H14V23H10V20H8V17H6V13H4V9H6V5H8V3H10Z"/>'
                '<path fill="currentColor" d="M10 3H14V5H16V9H18V13H16V17H14V20H12V21H10V18H8V14H6V10H8V6H10Z"/>'
                '<path fill="var(--accent-soft)" d="M10 4H12V10H10V15H8V11H7V9H9V6H10Z"/>'
                '<path fill="#171a20" d="M12 10H18V12H14V18H12Z"/>'
            ),
            '<path d="M11 2h2v11l3 3-1.4 1.4L11 13.8V2Zm-3 15.4h8V20H8v-2.6Z"/>',
            (
                '<circle cx="7.6" cy="18" r="2.6"/>'
                '<rect x="9.4" y="5.6" width="2" height="12.6"/>'
                '<path d="M9.4 5.6 19 3.4v4L9.4 9.6z"/>'
            ),
        ),
    },
    "Alex": {
        "icon": '★',
        "tone": NPC_CATALOG["Alex"]["tone"],
        "palette": dict(NPC_CATALOG["Alex"]["palette"]),
        "ornament": {
            "label": "橄榄球与哑铃",
            "kind": "laurel",
            "colors": {"line": "#9e644c", "highlight": "#e8b57c", "leaf": "#b69754", "leafHi": "#ead495"},
            "objects": (
                (
                    '<path fill="#20202c" d="M12 6H20V8H25V10H28V13H30V19H28V22H25V24H20V26H12V24H7V22H4V19H2V13H4V10H7V8H12Z"/>'
                    '<path fill="#995c3d" d="M12 8H20V10H25V12H27V15H28V18H26V21H23V23H19V24H12V22H7V20H5V17H4V14H6V11H9V10H12Z"/>'
                    '<path fill="#c98558" d="M12 9H19V11H23V13H25V16H7V14H8V12H12Z"/>'
                    '<path fill="#f1dec0" d="M7 11H9V21H7V19H6V13H7ZM23 11H25V13H26V19H25V21H23Z"/>'
                    '<path fill="#613b31" d="M11 17H22V19H11Z"/>'
                    '<path fill="#fff0cf" d="M11 15H21V17H11ZM12 13H14V19H12ZM17 13H19V19H17Z"/>'
                ),
                (
                    '<path fill="#20202c" d="M5 5H11V12H21V5H27V8H30V24H27V27H21V20H11V27H5V24H2V8H5Z"/>'
                    '<path fill="#667a8d" d="M6 7H9V25H6ZM23 7H26V25H23ZM4 10H6V22H4ZM26 10H28V22H26Z"/>'
                    '<path fill="#a8c0ca" d="M6 7H8V23H6ZM23 7H25V23H23ZM11 14H21V16H11Z"/>'
                    '<path fill="#8197a6" d="M11 16H21V18H11Z"/>'
                    '<path fill="#e6edf0" d="M6 8H8V12H6ZM23 8H25V12H23ZM13 14H19V15H13Z"/>'
                    '<path fill="#bb695d" d="M9 10H11V22H9ZM21 10H23V22H21Z"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M16 2H22V8H20V12H18V15H15V18H12V20H8V22H2V16H4V12H6V9H9V6H12V4H16Z"/>'
                '<path fill="currentColor" d="M16 4H20V8H18V12H16V15H13V17H10V19H6V20H4V16H6V12H8V9H11V7H14V5H16Z"/>'
                '<path fill="var(--accent-soft)" d="M15 6H18V8H16V10H14V12H12V14H10V16H8V18H6V15H8V13H10V11H12V9H14V7H15Z"/>'
                '<path fill="#171a20" d="M12 9H14V11H16V13H14V11H12V13H10V11H12ZM8 13H10V15H12V17H10V15H8Z"/>'
            ),
            (
                '<rect x="9.6" y="9.6" width="4.8" height="4.8" rx="1"/>'
                '<rect x="2.4" y="7.4" width="4.4" height="9.2" rx="1.6"/>'
                '<rect x="17.2" y="7.4" width="4.4" height="9.2" rx="1.6"/>'
            ),
            (
                '<ellipse cx="12" cy="15.4" rx="4.6" ry="4"/>'
                '<circle cx="6.6" cy="10.6" r="1.7"/>'
                '<circle cx="10" cy="8.4" r="1.7"/>'
                '<circle cx="14" cy="8.4" r="1.7"/>'
                '<circle cx="17.4" cy="10.6" r="1.7"/>'
            ),
        ),
    },
    "Emily": {
        "icon": '◇',
        "tone": NPC_CATALOG["Emily"]["tone"],
        "palette": dict(NPC_CATALOG["Emily"]["palette"]),
        "ornament": {
            "label": "宝石与彩色线轴",
            "kind": "ribbon",
            "colors": {"line": "#437f89", "highlight": "#b2e9de", "leaf": "#af6eab", "leafHi": "#e3addb"},
            "objects": (
                (
                    '<path fill="#20202c" d="M9 3H23V5H26V8H28V11H30V15H27V18H24V21H21V24H18V27H16V29H14V27H11V24H8V21H5V18H2V11H4V8H6V5H9Z"/>'
                    '<path fill="#4a9b9f" d="M10 5H22V7H25V10H27V12H28V14H25V17H22V20H19V23H17V25H15V26H13V23H10V20H7V17H4V12H6V9H8V7H10Z"/>'
                    '<path fill="#97e6d5" d="M10 5H15V12H5V11H7V8H10ZM5 14H14V24H12V21H9V18H6V16H5Z"/>'
                    '<path fill="#6571b6" d="M17 14H27V16H24V19H21V22H18V25H16Z"/>'
                    '<path fill="#d4f7e9" d="M10 6H13V9H10V11H7V9H9V7H10Z"/>'
                    '<path fill="#be8ac6" d="M17 5H21V8H23V12H17Z"/>'
                    '<path fill="#32676f" d="M4 12H28V14H17V25H15V14H4Z"/>'
                ),
                (
                    '<path fill="#20202c" d="M6 2H24V6H26V10H24V22H28V25H30V30H24V28H21V30H4V26H7V9H4V5H6Z"/>'
                    '<path fill="#ba8660" d="M8 4H22V6H24V8H6V6H8ZM6 27H23V28H6Z"/>'
                    '<rect fill="#edc79c" x="9" y="4" width="11" height="2"/>'
                    '<rect fill="#61b7b6" x="9" y="9" width="13" height="16"/>'
                    '<path fill="#dd86b5" d="M9 10H22V14H9ZM9 19H22V23H9ZM23 24H26V26H28V28H25V26H23Z"/>'
                    '<path fill="#b55693" d="M20 10H22V14H20ZM20 19H22V23H20Z"/>'
                    '<path fill="#a5e8db" d="M9 15H22V17H9ZM10 9H12V24H10Z"/>'
                    '<path fill="#ffe0e7" d="M10 11H12V13H10ZM10 20H12V22H10Z"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M8 2H16V4H19V6H21V8H23V12H21V14H19V17H16V20H14V22H10V20H8V17H5V14H3V12H1V8H3V6H5V4H8Z"/>'
                '<path fill="currentColor" d="M8 4H16V6H19V8H21V11H19V14H17V16H14V19H12V20H10V18H8V16H6V13H4V11H3V9H5V7H7V5H8Z"/>'
                '<path fill="var(--accent-soft)" d="M8 5H12V9H5V8H7V6H8ZM5 11H11V18H9V16H7V13H5Z"/>'
                '<path fill="#171a20" d="M3 9H21V11H13V19H11V11H3Z"/>'
            ),
            (
                '<circle cx="12" cy="12" r="3.2"/>'
                '<circle cx="12" cy="12" r="8.4" fill="none" stroke="currentColor" stroke-width="1.4"/>'
            ),
            '<path d="M12 3.4 13.5 10l6.6 1.6-6.6 1.6L12 19.8l-1.5-6.6-6.6-1.6L10.5 10Z"/>',
        ),
    },
    "Elliott": {
        "icon": '✒',
        "tone": NPC_CATALOG["Elliott"]["tone"],
        "palette": dict(NPC_CATALOG["Elliott"]["palette"]),
        "ornament": {
            "label": "羽毛笔墨水瓶与手稿",
            "kind": "paper",
            "colors": {"line": "#a77750", "highlight": "#e5c598", "leaf": "#c2996e", "leafHi": "#f0dcb4"},
            "objects": (
                (
                    '<path fill="#20202c" d="M23 2H29V10H27V14H24V17H21V20H17V23H19V28H17V30H5V28H3V22H5V18H11V14H14V10H17V7H20V4H23Z"/>'
                    '<path fill="#e2ceb0" d="M23 4H27V9H25V13H22V16H19V19H14V17H15V13H18V10H21V7H23Z"/>'
                    '<path fill="#fff0cf" d="M23 4H26V6H23V9H20V12H17V15H14V17H13V20H11V22H9V20H11V17H13V14H16V11H19V8H22V5H23Z"/>'
                    '<path fill="#ad8056" d="M19 13H23V15H19ZM15 17H19V19H15Z"/>'
                    '<path fill="#526574" d="M6 21H15V23H17V27H15V28H6V26H5V23H6Z"/>'
                    '<rect fill="#2f394c" x="8" y="22" width="7" height="5"/>'
                    '<rect fill="#8eacb9" x="6" y="23" width="2" height="3"/>'
                    '<rect fill="#c9a16b" x="5" y="19" width="10" height="2"/>'
                ),
                (
                    '<path fill="#20202c" d="M4 2H24V5H27V8H28V23H30V28H27V30H22V28H4Z"/>'
                    '<path fill="#c6a984" d="M6 4H22V9H26V26H6Z"/>'
                    '<path fill="#f0dfb8" d="M6 4H21V10H25V24H6Z"/>'
                    '<path fill="#fff1d3" d="M7 5H9V22H7ZM22 5H24V7H26V8H22Z"/>'
                    '<path fill="#987957" d="M11 8H18V10H11ZM9 13H22V14H9ZM9 17H22V18H9ZM9 21H17V22H9Z"/>'
                    '<path fill="#7d3d42" d="M22 21H26V23H28V27H26V28H23V26H21V23H22Z"/>'
                    '<path fill="#ba6670" d="M23 22H26V25H23Z"/>'
                    '<rect fill="#e0a09a" x="23" y="22" width="2" height="1"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M17 2H23V8H21V11H19V14H16V17H12V19H8V21H6V23H2V20H4V17H6V13H8V9H11V6H14V4H17Z"/>'
                '<path fill="currentColor" d="M17 4H21V8H19V11H17V14H14V16H10V18H7V16H8V13H10V10H12V8H15V6H17Z"/>'
                '<path fill="var(--accent-soft)" d="M17 4H20V6H17V8H15V10H13V12H11V14H9V16H7V18H5V20H4V21H3V20H5V17H7V14H9V11H11V9H13V7H15V5H17Z"/>'
                '<path fill="#171a20" d="M14 10H18V12H14ZM10 14H14V16H10Z"/>'
            ),
            '<path d="M2.6 15.6c2.4-2.6 4.8-2.6 7.2 0s4.8 2.6 7.2 0 4.6-2.6 4.4-.4c-.6 3-4 5.4-9.4 5.4S2.6 18.2 2.6 15.6Z"/>',
            (
                '<path d="M4.4 3.6h13.2v16.8H4.4z" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                '<path d="M6.6 8.4h8.8M6.6 12h8.8M6.6 15.6h5.6" fill="none" stroke="currentColor" stroke-width="1.4"/>'
            ),
        ),
    },
    "Harvey": {
        "icon": '✚',
        "tone": NPC_CATALOG["Harvey"]["tone"],
        "palette": dict(NPC_CATALOG["Harvey"]["palette"]),
        "ornament": {
            "label": "咖啡杯与医疗包",
            "kind": "vine",
            "colors": {"line": "#6b865e", "highlight": "#bfd39c", "leaf": "#719764", "leafHi": "#c5d9aa"},
            "objects": (
                (
                    '<path fill="#20202c" d="M3 10H24V12H28V14H30V22H28V24H23V27H20V29H7V27H4V23H3Z"/>'
                    '<path fill="#dcd3aa" d="M5 12H22V24H20V26H8V24H6V20H5ZM24 15H27V16H28V20H26V22H24Z"/>'
                    '<path fill="#779b68" d="M7 17H20V24H18V26H9V24H7Z"/>'
                    '<path fill="#4e7651" d="M17 17H20V23H18V25H16V24H17Z"/>'
                    '<path fill="#fcf0cb" d="M5 12H22V14H7V22H5Z"/>'
                    '<rect fill="#724834" x="7" y="14" width="13" height="2"/>'
                    '<path fill="#dfd7b5" d="M9 2H11V5H9V8H7V5H9ZM17 3H19V6H17V9H15V6H17Z"/>'
                    '<rect fill="#c4d3a1" x="9" y="18" width="2" height="4"/>'
                ),
                (
                    '<path fill="#20202c" d="M11 4H21V6H23V11H28V14H30V27H28V30H4V28H2V14H4V11H9V6H11Z"/>'
                    '<path fill="#9a795c" d="M11 6H21V11H19V8H13V11H11Z"/>'
                    '<path fill="#547958" d="M5 13H27V16H28V26H26V28H5V26H4V16H5Z"/>'
                    '<path fill="#739b6c" d="M6 13H25V16H6ZM5 17H8V25H5Z"/>'
                    '<path fill="#344f48" d="M25 17H28V26H26V28H7V26H25Z"/>'
                    '<rect fill="#e5dfbd" x="10" y="16" width="12" height="10"/>'
                    '<path fill="#bc6967" d="M14 17H18V20H21V23H18V25H14V23H11V20H14Z"/>'
                    '<rect fill="#f3edcf" x="11" y="16" width="4" height="1"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M8 2H16V8H22V16H16V22H8V16H2V8H8Z"/>'
                '<path fill="currentColor" d="M10 4H14V10H20V14H14V20H10V14H4V10H10Z"/>'
                '<path fill="var(--accent-soft)" d="M10 4H12V12H4V10H10Z"/>'
            ),
            (
                '<path d="M4 9.6h11v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5Z"/>'
                '<path d="M15.6 10.8h1.6a2.4 2.4 0 0 1 0 4.8h-1.6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
            ),
            (
                '<circle cx="8" cy="12" r="4.4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                '<circle cx="16" cy="12" r="4.4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                '<path d="M11.6 12h.8" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            ),
        ),
    },
    "Sebastian": {
        "icon": '◢',
        "tone": NPC_CATALOG["Sebastian"]["tone"],
        "palette": dict(NPC_CATALOG["Sebastian"]["palette"]),
        "ornament": {
            "label": "游戏手柄与蝙蝠",
            "kind": "cable",
            "colors": {"line": "#59638e", "highlight": "#b7b2df", "leaf": "#7276ae", "leafHi": "#bdbbe7"},
            "objects": (
                (
                    '<path fill="#20202c" d="M15 2H20V4H17V7H24V9H27V12H29V18H30V25H28V28H24V26H21V23H11V26H8V28H4V26H2V18H3V12H5V9H8V7H15Z"/>'
                    '<path fill="#535875" d="M8 9H24V11H26V14H27V20H28V25H25V24H22V21H10V24H7V26H4V19H5V13H7V11H8Z"/>'
                    '<path fill="#898cb0" d="M9 9H23V11H8V14H6V18H4V15H5V12H7V10H9Z"/>'
                    '<path fill="#353b54" d="M23 18H27V23H25V24H22V21H12V19H23Z"/>'
                    '<path fill="#20202c" d="M8 12H11V15H14V18H11V21H8V18H5V15H8Z"/>'
                    '<rect fill="#b9c6d5" x="8" y="14" width="3" height="3"/>'
                    '<rect fill="#b176a4" x="23" y="13" width="3" height="3"/>'
                    '<rect fill="#719fb8" x="19" y="17" width="3" height="3"/>'
                    '<rect fill="#c5bcd9" x="16" y="13" width="3" height="1"/>'
                ),
                (
                    '<path fill="#20202c" d="M12 3H14V7H18V3H20V10H23V7H26V4H30V16H28V19H24V22H21V25H18V29H14V25H11V22H8V19H4V16H2V4H6V7H9V10H12Z"/>'
                    '<path fill="#565179" d="M13 8H19V13H23V10H26V8H28V15H26V17H23V20H20V22H18V26H15V23H12V20H9V17H5V15H4V8H6V10H9V13H13Z"/>'
                    '<path fill="#9384b0" d="M4 8H6V10H9V13H12V15H9V14H6V12H4ZM22 13H25V10H28V13H26V15H23V17H21Z"/>'
                    '<path fill="#363650" d="M13 17H19V23H17V26H15V23H13Z"/>'
                    '<path fill="#c8b4d9" d="M13 12H15V14H13ZM17 12H19V14H17Z"/>'
                    '<rect fill="#be83a1" x="15" y="17" width="2" height="1"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M8 3H10V5H14V3H16V8H18V6H20V4H23V11H21V15H18V18H14V21H10V18H6V15H3V11H1V4H4V6H6V8H8Z"/>'
                '<path fill="currentColor" d="M9 5H10V7H14V5H15V11H17V9H19V7H21V11H19V14H17V16H14V14H13V19H11V14H10V16H7V14H5V11H3V7H5V9H7V11H9Z"/>'
                '<path fill="var(--accent-soft)" d="M3 7H5V9H7V11H5V10H3ZM17 9H19V7H21V10H19V11H17Z"/>'
                '<rect fill="#171a20" x="10" y="9" width="1" height="2"/>'
                '<rect fill="#171a20" x="13" y="9" width="1" height="2"/>'
            ),
            (
                '<rect x="2.4" y="8" width="19.2" height="9.6" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.7"/>'
                '<path d="M6 11h2.4M10.6 11H13M14.6 11h2.4M6 14h12" fill="none" stroke="currentColor" stroke-width="1.3"/>'
            ),
            (
                '<circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" stroke-width="2"/>'
                '<path d="M12 3.8v16.4M3.8 12h16.4" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".85"/>'
            ),
        ),
    },
    "Shane": {
        "icon": '☕',
        "tone": NPC_CATALOG["Shane"]["tone"],
        "palette": dict(NPC_CATALOG["Shane"]["palette"]),
        "ornament": {
            "label": "小鸡与咖啡杯",
            "kind": "wheat",
            "colors": {"line": "#8b7654", "highlight": "#e6c58b", "leaf": "#ba9e66", "leafHi": "#f0d8a2"},
            "objects": (
                (
                    '<path fill="#20202c" d="M17 2H20V4H23V7H26V11H30V15H27V21H24V25H21V28H22V30H15V28H16V26H10V28H11V30H5V28H7V25H4V21H2V13H5V15H10V12H13V8H15V5H17Z"/>'
                    '<path fill="#e6b968" d="M16 8H22V10H25V17H24V21H21V24H9V23H6V20H4V17H11V14H15V10H16Z"/>'
                    '<path fill="#fff0bc" d="M17 9H21V11H23V17H21V20H17V22H9V20H6V17H12V14H16V11H17Z"/>'
                    '<path fill="#c9924f" d="M10 17H16V19H18V21H14V23H10V21H8V19H10Z"/>'
                    '<path fill="#df8f70" d="M17 4H19V6H21V8H16V6H17Z"/>'
                    '<path fill="#e6a24d" d="M25 12H28V14H25ZM8 26H10V29H6V28H8ZM17 26H19V29H16V28H17Z"/>'
                    '<rect fill="#20202c" x="21" y="11" width="2" height="2"/>'
                    '<rect fill="#fff9da" x="15" y="14" width="3" height="2"/>'
                ),
                (
                    '<path fill="#20202c" d="M2 10H24V12H28V14H30V22H28V25H23V28H20V30H7V28H4V24H2Z"/>'
                    '<path fill="#54849b" d="M4 12H22V25H19V28H8V26H6V22H4ZM24 15H27V17H28V20H26V22H24Z"/>'
                    '<path fill="#86b6c2" d="M4 12H22V15H7V24H5V21H4Z"/>'
                    '<path fill="#36576c" d="M19 16H22V25H19V28H8V26H17V24H19Z"/>'
                    '<rect fill="#d9d4b7" x="6" y="12" width="14" height="3"/>'
                    '<rect fill="#634738" x="8" y="13" width="12" height="2"/>'
                    '<path fill="#ccc9b4" d="M8 2H10V5H8V8H6V5H8ZM16 3H18V6H16V8H14V6H16Z"/>'
                    '<rect fill="#b5d4d2" x="7" y="17" width="2" height="6"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M2 7H18V9H22V11H24V17H22V19H17V21H14V23H6V21H3V18H2Z"/>'
                '<path fill="currentColor" d="M4 9H16V18H14V20H6V18H4ZM18 11H21V13H22V15H20V17H18Z"/>'
                '<path fill="var(--accent-soft)" d="M4 9H16V11H6V17H4ZM7 1H9V3H7V5H5V3H7ZM13 1H15V3H13V5H11V3H13Z"/>'
                '<path fill="#171a20" d="M18 13H20V15H18Z"/>'
            ),
            (
                '<circle cx="12" cy="13.6" r="5.6"/>'
                '<path d="M12 8V5.2l3-1.4v2.6z"/>'
                '<circle cx="9.8" cy="12.4" r=".9" fill="#0d0e15"/>'
                '<path d="M11.4 16.2h3.2l-1.6 2z"/>'
            ),
            (
                '<path d="M8.4 3.2h5.2v6.4a2.6 2.6 0 0 1-5.2 0Z"/>'
                '<path d="M10 9.6h2v11h-2z"/>'
                '<path d="M9 20.6h4v1.4H9z"/>'
            ),
        ),
    },
    "Sophia": {
        "icon": '✿',
        "tone": NPC_CATALOG["Sophia"]["tone"],
        "palette": dict(NPC_CATALOG["Sophia"]["palette"]),
        "ornament": {
            "label": "葡萄串与葡萄叶粉花",
            "kind": "grapevine",
            "colors": {"line": "#779658", "highlight": "#c6d598", "leaf": "#7ea466", "leafHi": "#c9dca1"},
            "objects": (
                (
                    '<path fill="#20202c" d="M16 2H19V5H23V3H29V8H26V11H25V17H23V23H20V27H18V30H13V28H10V24H7V20H4V15H2V11H4V8H9V6H14V4H16Z"/>'
                    '<path fill="#6e8f53" d="M18 4H19V7H23V5H27V7H24V9H19V11H15V8H17Z"/>'
                    '<path fill="#b5c988" d="M22 6H26V7H23V8H21V7H22Z"/>'
                    '<path fill="#63477f" d="M5 10H10V9H16V10H22V12H24V16H21V20H20V23H17V28H14V26H12V22H9V18H6V16H4V12H5Z"/>'
                    '<path fill="#ac79bd" d="M5 10H10V15H5ZM12 9H16V14H11V11H12ZM18 11H22V16H17V13H18ZM8 16H13V21H8ZM15 17H20V22H15ZM12 23H17V27H13V26H12Z"/>'
                    '<path fill="#d4a7db" d="M5 10H8V12H5ZM12 9H14V11H12ZM18 11H20V13H18ZM8 16H10V18H8ZM15 17H17V19H15ZM13 23H15V25H13Z"/>'
                    '<path fill="#875795" d="M8 13H10V15H8ZM14 12H16V14H14ZM20 14H22V16H20ZM11 19H13V21H11ZM18 20H20V22H18ZM15 25H17V27H15Z"/>'
                ),
                (
                    '<path fill="#20202c" d="M12 2H17V5H21V8H25V12H23V16H19V20H15V24H12V29H9V26H10V23H5V20H2V15H5V11H3V7H8V5H12Z"/>'
                    '<path fill="#70985c" d="M13 4H15V7H19V10H23V12H21V15H18V18H14V21H10V23H6V20H4V16H7V12H6V9H10V7H13Z"/>'
                    '<path fill="#a8c87b" d="M13 6H15V10H13V13H10V17H7V19H5V16H8V12H10V9H13Z"/>'
                    '<path fill="#446e47" d="M14 10H16V15H19V17H15V20H13V24H11V27H10V23H11V18H8V16H12V13H14Z"/>'
                    '<path fill="#20202c" d="M22 15H26V18H30V23H28V27H24V30H20V27H16V23H18V19H21V18H22Z"/>'
                    '<path fill="#cf7da6" d="M22 17H24V21H28V23H26V26H23V28H21V25H18V22H22Z"/>'
                    '<path fill="#f1b6cf" d="M22 17H24V20H22ZM19 21H22V23H19ZM25 21H28V23H25ZM21 25H23V28H21Z"/>'
                    '<rect fill="#f6daa0" x="22" y="22" width="3" height="3"/>'
                    '<rect fill="#fff0c5" x="22" y="22" width="1" height="1"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M10 1H14V3H16V7H14V9H15V8H19V9H21V11H23V15H21V17H17V15H15V16H16V20H14V23H10V21H8V17H10V15H9V16H5V15H3V13H1V9H3V7H7V9H9V8H8V4H10Z"/>'
                '<path fill="currentColor" d="M10 3H14V7H12V9H10ZM3 9H7V11H9V13H5V12H3ZM17 10H19V12H21V15H17V13H15V11H17ZM10 17H14V20H12V21H10ZM10 10H14V14H10Z"/>'
                '<path fill="var(--accent-soft)" d="M10 3H12V5H10ZM3 9H5V11H3ZM17 10H19V12H17ZM10 17H12V19H10ZM10 10H14V14H10Z"/>'
            ),
            (
                '<circle cx="8.6" cy="9" r="3.2"/>'
                '<circle cx="15.4" cy="9" r="3.2"/>'
                '<circle cx="12" cy="14.6" r="3.4"/>'
                '<path d="M12 5.4l1.6 2.6h-3.2z"/>'
            ),
            '<path d="M12 2.6 13.9 9h6.7l-5.4 4 2 6.4L12 15.6 6.8 19.4l2-6.4-5.4-4h6.7Z"/>',
        ),
    },
    "Wizard": {
        "icon": '✧',
        "tone": NPC_CATALOG["Wizard"]["tone"],
        "palette": dict(NPC_CATALOG["Wizard"]["palette"]),
        "ornament": {
            "label": "水晶球与魔法书",
            "kind": "arcane",
            "colors": {"line": "#9361ae", "highlight": "#d9b0ed", "leaf": "#b48c57", "leafHi": "#ebd19e"},
            "objects": (
                (
                    '<path fill="#20202c" d="M11 2H21V4H25V7H28V12H30V17H28V21H24V24H26V27H28V30H4V27H6V24H8V22H4V18H2V11H4V7H7V4H11Z"/>'
                    '<path fill="#8261a5" d="M11 4H21V6H24V9H26V12H28V17H26V20H23V22H9V20H6V17H4V12H6V8H9V6H11Z"/>'
                    '<path fill="#b69cd3" d="M11 5H19V7H22V10H23V15H21V18H18V20H11V18H8V15H6V12H8V8H11Z"/>'
                    '<path fill="#e5d8ec" d="M11 6H16V8H11V10H9V14H7V10H9V8H11Z"/>'
                    '<path fill="#668cac" d="M19 11H23V14H26V17H24V19H21V21H14V19H17V16H19Z"/>'
                    '<path fill="#d9b573" d="M9 24H23V26H25V28H7V26H9Z"/>'
                    '<path fill="#936943" d="M10 26H22V28H10Z"/>'
                    '<path fill="#f0dfb2" d="M16 11H18V13H20V15H18V17H16V15H14V13H16Z"/>'
                ),
                (
                    '<path fill="#20202c" d="M5 2H26V5H29V28H26V30H5V28H3V5H5Z"/>'
                    '<path fill="#654775" d="M6 4H25V6H27V27H25V28H6V26H5V6H6Z"/>'
                    '<path fill="#9270a5" d="M8 4H24V6H26V24H8Z"/>'
                    '<path fill="#d8c49b" d="M8 25H26V27H8Z"/>'
                    '<path fill="#efe1b7" d="M9 25H24V26H9Z"/>'
                    '<path fill="#c2a16a" d="M8 5H11V7H8ZM22 5H25V8H23V7H22ZM8 21H11V24H8ZM22 21H25V24H22Z"/>'
                    '<path fill="#503b64" d="M16 8H19V11H22V14H24V17H21V20H17V22H14V19H11V15H13V11H16Z"/>'
                    '<path fill="#e7c888" d="M16 10H18V13H21V15H22V16H19V19H16V20H15V17H13V14H15V12H16Z"/>'
                    '<rect fill="#ad76c9" x="16" y="14" width="3" height="3"/>'
                    '<rect fill="#e6b8e7" x="16" y="14" width="1" height="1"/>'
                ),
            ),
        },
        "motifs": (
            (
                '<path fill="#171a20" d="M11 1H13V4H15V7H17V8H23V11H21V13H19V15H18V17H19V21H16V20H14V19H10V20H8V21H5V17H6V15H5V13H3V11H1V8H7V7H9V4H11Z"/>'
                '<path fill="currentColor" d="M11 4H13V7H15V10H20V11H18V13H16V16H17V18H15V17H13V16H11V17H9V18H7V16H8V13H6V11H4V10H9V7H11Z"/>'
                '<path fill="var(--accent-soft)" d="M11 5H13V10H16V12H12V14H10V16H8V14H9V12H7V10H11Z"/>'
            ),
            (
                '<path d="M11.2 3.4h1.6v13.2h-1.6z"/>'
                '<circle cx="12" cy="4.6" r="2.8"/>'
                '<path d="M8.8 19.4h6.4v1.8H8.8z"/>'
            ),
            (
                '<path d="M12 2.8 20 7.4v9.2L12 21.2 4 16.6V7.4Z" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                '<path d="M12 8.2 15.6 12 12 15.8 8.4 12Z"/>'
            ),
        ),
    },
}


# Keep the approved nine finished illustrations intact. New character assignments
# come from the shipped catalog, generated from the single authoritative spec.
for _npc_id, _definition in NPC_CATALOG.items():
    if _npc_id in NPC_BUBBLE_ELEMENTS:
        continue
    _palette = _definition["palette"]
    _objects = tuple(OBJECT_SVGS[key] for key in _definition["objects"])
    _glyph = '<svg width="24" height="24" viewBox="0 0 32 32">' + OBJECT_SVGS[_definition["glyph"]] + '</svg>'
    NPC_BUBBLE_ELEMENTS[_npc_id] = {
        "icon": "✦",
        "tone": _definition["tone"],
        "palette": dict(_palette),
        "ornament": {
            "label": "与".join(OBJECT_CATALOG[key]["label"] for key in _definition["objects"]),
            "kind": _definition["kind"],
            "colors": {
                "line": _palette["border"],
                "highlight": _palette["accentSoft"],
                "leaf": _palette["fruit"],
                "leafHi": _palette["fruitHi"],
            },
            "objects": _objects,
        },
        "motifs": (_glyph,) + tuple('<svg width="24" height="24" viewBox="0 0 32 32">' + obj + '</svg>' for obj in _objects),
    }
