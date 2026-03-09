# 导出说明

当前支持导出整本小说为：

- txt
- md
- docx
- pdf

接口：

```text
GET /api/v1/novels/{novel_id}/export?format=txt
GET /api/v1/novels/{novel_id}/export?format=md
GET /api/v1/novels/{novel_id}/export?format=docx
GET /api/v1/novels/{novel_id}/export?format=pdf
```

说明：

- `txt`：纯文本版本
- `md`：Markdown 版本
- `docx`：Word 文档
- `pdf`：可打印 PDF

这个版本已经修复中文文件名导出时的响应头编码问题。
