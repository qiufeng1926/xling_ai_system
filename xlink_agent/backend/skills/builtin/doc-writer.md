---
name: doc-writer
slug: doc-writer
description: 生成 Word / Excel / PPT / PDF 办公文档
version: 1
tools:
  - file_write_docx
  - file_write_xlsx
  - file_write_pptx
  - file_write_pdf
  - file_write_markdown
  - kb_search
  - file_list
permissions:
  confirm:
    - file_delete
---

# 文档生成 Skill

根据用户需求生成可下载的办公文档，写入用户工作区。内容尽量结构化、可直接交付。
若用户提到知识库中的材料，先 `kb_search` 再写作。
