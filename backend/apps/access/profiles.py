from apps.access.models import ReaderProfile

DEFAULT_READER_PROFILES = [
    {
        "name": "RFID hexadecimal 8 dígitos",
        "credential_type": "RFID",
        "normalization": [
            {"op": "trim"},
            {"op": "upper"},
            {"op": "regex_extract", "pattern": "([0-9A-F]+)"},
            {"op": "pad_left", "length": 8, "char": "0"},
        ],
        "min_length": 8,
        "max_length": 8,
    },
    {
        "name": "RFID decimal 10 dígitos",
        "credential_type": "RFID",
        "normalization": [
            {"op": "trim"},
            {"op": "regex_extract", "pattern": "([0-9]+)"},
            {"op": "strip_leading_zeros"},
            {"op": "pad_left", "length": 10, "char": "0"},
        ],
        "min_length": 10,
        "max_length": 10,
    },
    {
        "name": "ID numérico de lector de huella",
        "credential_type": "FINGERPRINT",
        "normalization": [
            {"op": "trim"},
            {"op": "regex_extract", "pattern": "([0-9]+)"},
            {"op": "strip_leading_zeros"},
        ],
        "min_length": 1,
        "max_length": 20,
    },
]


def create_default_reader_profiles(organization) -> list[ReaderProfile]:
    created = []
    for spec in DEFAULT_READER_PROFILES:
        profile, was_created = ReaderProfile.all_objects.get_or_create(
            organization=organization,
            name=spec["name"],
            defaults={
                "credential_type": spec["credential_type"],
                "normalization": spec["normalization"],
                "min_length": spec["min_length"],
                "max_length": spec["max_length"],
            },
        )
        if was_created:
            created.append(profile)
    return created
