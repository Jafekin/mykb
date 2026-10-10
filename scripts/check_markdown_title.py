"""Regression checks for code comments incorrectly used as article titles."""
import unittest
from markdown_title import article_title, article_excerpt


class TitleTests(unittest.TestCase):
    def test_excerpt_removes_metadata(self):
        body = '# Title\n\n- **难度**：MEDIUM\n- **分类**：算法\n- **时间限制**：5000 ms\n- **内存限制**：256 MB\n\n## 题目说明\n\n实现 `linear_backward`，返回输入梯度。\n\n## 示例\n后续内容'
        self.assertEqual(article_excerpt(body), '实现 linear_backward，返回输入梯度。')

    def test_excerpt_uses_first_intro_and_skips_code(self):
        body = '---\ntitle: Title\n---\n# Title\n\n```python\n# comment\n```\n\n> 请实现 [滑动窗口](https://example.com)。\n\n## 解答\n后续内容'
        self.assertEqual(article_excerpt(body), '请实现 滑动窗口。')

    def test_python_comment(self):
        self.assertEqual(article_title('## `nn.Embedding` 详解\n```python\n# 返回第2行: [-0.3, 0.8, 0.2, -0.1]\n```', 'fallback'), 'nn.Embedding 详解')

    def test_only_code(self):
        self.assertEqual(article_title('```python\n# comment\n```', 'filename'), 'filename')

    def test_top_level_preferred(self):
        self.assertEqual(article_title('## Intro\n# Article ###\n', 'fallback'), 'Article')

    def test_frontmatter(self):
        self.assertEqual(article_title('---\ntitle: "Metadata title"\n---\n## Section\n```\n# code\n```', 'fallback'), 'Metadata title')

    def test_long_fence(self):
        self.assertEqual(article_title('````python\n```\n# code\n````\n# Real title', 'fallback'), 'Real title')

    def test_tilde_fence(self):
        self.assertEqual(article_title('  ~~~python\n# comment\n  ~~~\n## Real title', 'fallback'), 'Real title')

    def test_indented_code(self):
        self.assertEqual(article_title('    # code\n\n## Real title', 'fallback'), 'Real title')


if __name__ == '__main__':
    unittest.main()
