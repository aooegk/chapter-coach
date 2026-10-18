# Changelog

本项目遵循语义化版本。日期为本地发布日期。

## [1.1.0] - 2026-10-17

### Added

- `review.html` 默认只展示未满分题；全部答对时显示“全部答对”状态。
- `build_review.py --include-correct`，需要完整逐题回顾时可展开所有题目。
- `CHANGELOG.md`。

### Changed

- 结果页摘要新增“答对 X / 共 Y 题”“错题 N 题”。
- README 重新梳理：学习流程并入“使用方法”，删除重复章节。
- 答题记录说明更明确：`submission.json`、`media/`、`attempts/<quiz_id>.jsonl` 都会保留。

### Fixed

- 结果页不再用正确题稀释错题回顾。

## [1.0.0] - 2026-10-17

### Added

- 首个公开版本：PPT 逐章学习、课程画像、配置闸门、离线试卷、图片作答、rubric 批改、学习状态与报告。
- 内联 MathJax 3.2.2，支持完整 LaTeX。
- 跨平台能力分级与多种回传通道。

[1.1.0]: https://github.com/aooegk/chapter-coach/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/aooegk/chapter-coach/releases/tag/v1.0.0
