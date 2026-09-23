---
title: Markdown 图片测试
date: 2026-09-23
---

# Markdown 图片解析测试

这份文档用于测试 Markdown 图片迁移工具。

## 1. 当前目录下的相对路径

最常见的 Markdown 图片：

111![avatar](./images/avatar.png)

普通正文继续。

---

## 2. 上级目录的相对路径

图片位于当前 Markdown 文件的上级目录：

![avatar](../assets/avatar.jpg)

---

## 3. URL Encode 的文件名

文件名中包含空格，Markdown 中使用 `%20`：

![avatar](images/foo%20bar.png)

实际文件名可能是：

`images/foo bar.png`

---

## 4. 包含空格的绝对路径

使用 `< >` 包裹 URL，可以处理路径中的空格：

![](/Users/foo/My Images/a.png)

---

## 5. Reference Style 图片

这里使用引用式图片：

![foo][image1]

正文可以位于图片和 definition 之间。

这里还有一些其他内容。

[image1]: ./images/foo.png

---

## 6. HTML img 标签

Markdown 中也可以直接嵌入 HTML：

<img src="./images/foo.png">

带其他属性的情况：

<img
  src="../assets/banner.png"
  alt="Banner"
  width="600"
>

---

## 7. 图片带 title

Markdown 图片还可能带有 title：

![avatar](./images/avatar-with-title.png "这是头像")

---

## 8. URL 中包含空格

使用尖括号：

![foo](<./images/foo bar.png>)

---

## 9. 远程图片

这种图片已经是远程 URL，迁移工具通常应该忽略：

![remote](https://example.com/images/avatar.png)

HTTP URL：

![remote](http://example.com/a.jpg)

Protocol-relative URL：

![remote](//cdn.example.com/a.png)

---

## 10. Data URL

这种也不应该作为本地图片上传：

![inline](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA)

---

## 11. 普通链接，不是图片

注意这里没有 `!`，所以不是图片：

[查看图片](./images/avatar.png)

---

## 12. Inline Code 中出现图片语法

下面只是代码，不应该被识别成真正的图片：

`![avatar](./images/not-a-real-image.png)`

---

## 13. Code Block 中出现图片语法

下面整个代码块里的内容都不应该被当成真正图片：

```md
# 示例 Markdown

![avatar](./images/fake-image.png)

![foo][fake-image]

[fake-image]: ./images/fake.png

<img src="./images/fake-html-image.png">
