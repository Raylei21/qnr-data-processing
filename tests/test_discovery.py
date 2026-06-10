from qnr_data_processing.discovery import _reconcile_options


def test_reconcile_options_uses_observed_labels_and_appends_new_values():
    options, warnings = _reconcile_options(
        [
            "直播和集锦都不看，只看比赛新闻/结果",
            "三年及以上",
        ],
        [
            "直播和集锦都不看，只看比赛新闻或结果",
            "三年以上",
            "完全不关注",
        ],
    )

    assert options == [
        "直播和集锦都不看，只看比赛新闻或结果",
        "三年以上",
        "完全不关注",
    ]
    assert len(warnings) == 3


def test_reconcile_options_keeps_unobserved_questionnaire_options():
    options, warnings = _reconcile_options(["是", "否"], ["是"])

    assert options == ["是", "否"]
    assert warnings == []
