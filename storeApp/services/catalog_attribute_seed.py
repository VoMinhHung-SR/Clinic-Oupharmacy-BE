"""Provisional filterable attribute dictionary (seed / reference)."""

from __future__ import annotations

# code, label, facet_type, sort_order, default options [(slug, label), ...]
CATALOG_ATTRIBUTE_SEED = [
    (
        "target_user",
        "Đối tượng sử dụng",
        "multiple",
        10,
        [
            ("tat-ca", "Tất cả"),
            ("tre-em", "Trẻ em"),
            ("tre-so-sinh", "Trẻ sơ sinh"),
            ("tre-nho", "Trẻ nhỏ"),
            ("nguoi-lon", "Người lớn"),
            ("nguoi-cao-tuoi", "Người cao tuổi"),
            ("phu-nu-mang-thai", "Phụ nữ mang thai"),
        ],
    ),
    (
        "skin_type",
        "Loại da",
        "multiple",
        20,
        [
            ("da-kho", "Da khô"),
            ("da-nhay-cam", "Da nhạy cảm"),
            ("da-mun", "Da mụn"),
            ("da-dau", "Da dầu"),
            ("da-hon-hop", "Da hỗn hợp"),
            ("da-thuong", "Da thường"),
        ],
    ),
    (
        "flavor",
        "Mùi vị / Mùi hương",
        "multiple",
        30,
        [
            ("cam", "Cam"),
            ("chanh", "Chanh"),
            ("dau", "Dâu"),
            ("bac-ha", "Bạc hà"),
            ("vanilla", "Vanilla"),
            ("khong-mui", "Không mùi"),
        ],
    ),
    (
        "indication",
        "Chỉ định",
        "multiple",
        40,
        [],
    ),
    (
        "dosage_form",
        "Dạng bào chế",
        "multiple",
        50,
        [
            ("vien", "Viên"),
            ("siro", "Siro"),
            ("bot", "Bột"),
            ("dung-dich", "Dung dịch"),
            ("kem", "Kem"),
            ("gel", "Gel"),
            ("xit", "Xịt"),
        ],
    ),
    (
        "brand_origin",
        "Xuất xứ thương hiệu",
        "multiple",
        60,
        [],
    ),
]
