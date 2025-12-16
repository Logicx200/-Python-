# Markdown Base64图片上传工具

## 🖼️ 项目概述
一个专业级的Markdown图片管理工具，专门用于处理Markdown文档中的Base64内嵌图片。支持将Base64编码的图片批量上传到SM.MS图床，并自动替换为在线链接，显著减小文档体积。

## ✨ 核心特性
- **智能检测**：自动识别多种格式的Base64图片
- **批量上传**：支持大量图片的并发处理
- **SM.MS集成**：与流行的免费图床无缝集成
- **图片预览**：可视化查看所有检测到的图片
- **格式修复**：自动验证和修复Base64格式问题
- **详细日志**：完整的处理记录和错误报告
- **配置持久化**：保存API Token和用户设置

## 📦 系统要求
```bash
# 必需依赖
pip install requests pillow

# 可选：用于更好的GUI体验
# pip install ttkthemes
```

## 🚀 快速开始
```bash
python "Markdown Base64图片上传工具.py"
```

## 🔑 SM.MS API配置

### 获取API Token
1. 访问 https://sm.ms
2. 注册账号并登录
3. 进入Dashboard → API Token
4. 生成新的Token

### API限制
| 账户类型 | 上传限制 | 存储限制 | 带宽限制 |
|----------|----------|----------|----------|
| 免费用户 | 10张/小时 | 5GB | 10GB/月 |
| VIP用户 | 无限制 | 50GB | 100GB/月 |

## 🖥️ 界面详解

### 主界面布局
```
┌─────────────────────────────────────────────┐
│ SM.MS API Token: [输入框] [显示][保存][获取] │
├─────────────────────────────────────────────┤
│ Markdown文件: [路径] [浏览][预览图片]        │
│ 输出选项: ○同目录 ●覆盖 ○自定义 [浏览]        │
├─────────────────────────────────────────────┤
│ [✓]跳过已存在 [✓]备份原文件                  │
│ [✓]验证Base64 [✓]自动修复Base64             │
├─────────────────────────────────────────────┤
│ 处理日志:                                   │
│ [详细的日志信息...]                          │
├─────────────────────────────────────────────┤
│ [============== 进度条 ==============]      │
│ 状态：就绪              [开始处理]           │
└─────────────────────────────────────────────┘
```

## 🔍 Base64图片检测

### 支持的格式
```markdown
![] (data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...)
![alt文本](data:image/jpeg;base64,/9j/4AAQSkZJRg...)
<img src="data:image/gif;base64,R0lGODlh...">
background-image: url(data:image/webp;base64,UklGR...)
```

### 图片格式支持
| 格式 | MIME类型 | 支持程度 |
|------|----------|----------|
| PNG | image/png | ✅ 完整 |
| JPEG | image/jpeg | ✅ 完整 |
| GIF | image/gif | ✅ 完整 |
| WebP | image/webp | ✅ 完整 |
| BMP | image/bmp | ⚠️ 基本 |
| SVG | image/svg+xml | ⚠️ 有限 |

## 🔧 技术实现

### Base64处理流程
```python
1. 正则匹配：在Markdown中查找Base64字符串
2. 数据清洗：移除空白字符和data: URI前缀
3. 格式验证：验证Base64编码有效性
4. 图片解码：解码为二进制数据
5. 类型检测：识别图片格式和尺寸
```

### 上传流程
```python
1. 准备请求：设置API Token和Headers
2. 编码转换：Base64 → 二进制数据
3. 文件包装：创建multipart/form-data
4. 发送请求：POST到SM.MS API
5. 解析响应：提取URL和错误信息
6. 重试机制：失败时自动重试3次
```

## 💡 使用示例

### 示例1：基础使用
1. 输入有效的SM.MS API Token
2. 选择包含Base64图片的Markdown文件
3. 选择输出选项（推荐"同目录"）
4. 点击"开始处理"
5. 查看处理日志，确认结果

### 示例2：图片预览
1. 选择Markdown文件后
2. 点击"预览图片"按钮
3. 在新窗口查看所有检测到的图片
4. 可以查看每张图片的详细信息

### 示例3：批量处理脚本
```bash
#!/bin/bash
# 批量处理多个Markdown文件

API_TOKEN="your_api_token_here"

for md_file in docs/*.md; do
    echo "处理文件: $md_file"
    python -c "
import sys
sys.path.append('.')
from md_image_processor import MarkdownImageProcessor

processor = MarkdownImageProcessor('$API_TOKEN')
result = processor.process_file('$md_file', '${md_file}_processed.md')
print(f'成功: {result[\"success\"]}, 失败: {result[\"failed\"]}')
"
done
```

## 🛠️ 高级配置

### 配置文件位置
```
~/.md_img_uploader_config.json
```

### 配置文件格式
```json
{
  "api_token": "your_api_token_here",
  "last_directory": "/path/to/last/used/dir",
  "settings": {
    "skip_existing": true,
    "backup_original": true,
    "verify_base64": true,
    "fix_base64": true
  }
}
```

### 自定义处理选项
```python
# 可以修改源码中的常量
MAX_RETRY_COUNT = 5           # 最大重试次数
TIMEOUT = 30                  # 上传超时时间(秒)
CHUNK_SIZE = 8192             # 分块大小
VALID_IMAGE_TYPES = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
```

## 🔍 故障排除

### 常见问题及解决

#### 问题1：API Token无效
```
错误：API错误: unauthorized
解决：
1. 检查Token是否正确
2. 重新生成Token
3. 确认账户状态正常
```

#### 问题2：图片上传失败
```
错误：上传失败: 网络错误
解决：
1. 检查网络连接
2. 增加超时时间
3. 降低图片质量或尺寸
```

#### 问题3：Base64格式错误
```
错误：Base64数据无效
解决：
1. 启用"自动修复Base64"
2. 手动检查Base64字符串
3. 确保没有多余的换行或空格
```

#### 问题4：重复图片错误
```
错误：图片已存在
解决：
1. 启用"跳过已存在图片"
2. 程序会自动使用现有链接
```

### 调试模式
```python
# 在代码中添加调试信息
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 性能优化

### 批量处理建议
```python
# 对于大量图片，建议：
1. 分批处理：每次处理10-20个文件
2. 网络优化：确保稳定的网络连接
3. 内存管理：大文件分段处理
```

### 上传速度参考
| 图片数量 | 平均大小 | 预计时间 | 备注 |
|----------|----------|----------|------|
| 10张 | 100KB/张 | 30-60秒 | 正常 |
| 50张 | 500KB/张 | 5-10分钟 | 需要稳定网络 |
| 100张 | 1MB/张 | 15-30分钟 | 建议分批 |

## 🔄 替代方案

### 其他图床选项
1. **imgur**：无需注册，但有速率限制
2. **github**：免费，但需要仓库
3. **cloudinary**：免费额度充足
4. **七牛云**：国内CDN加速
5. **阿里云OSS**：按量付费

### 修改代码支持其他图床
```python
class CustomImageUploader:
    def upload_image(self, image_data, image_type):
        # 实现自定义上传逻辑
        # 返回格式：{"url": "图片URL", "success": True}
        pass
```

## 📚 API参考

### SM.MS API v2
```python
POST https://sm.ms/api/v2/upload
Headers: {"Authorization": "Your_API_Token"}
Body: multipart/form-data
Response: {"success": true, "data": {"url": "...", "hash": "..."}}
```

### 错误代码
| 代码 | 含义 | 处理建议 |
|------|------|----------|
| success | 上传成功 | 继续处理 |
| image_repeated | 图片重复 | 使用现有链接 |
| unauthorized | Token无效 | 检查Token |
| upload failed | 上传失败 | 重试 |

## 🛡️ 安全和隐私

### 数据保护
1. **本地处理**：所有图片在本地解码和编码
2. **Token安全**：Token本地加密存储
3. **不保留数据**：处理后删除临时文件
4. **可选备份**：原文件备份可选

### 使用建议
1. **敏感图片**：不要上传敏感或私有图片
2. **版权注意**：确保拥有图片版权
3. **定期清理**：定期清理SM.MS账户中的图片
4. **备份重要图片**：重要图片保留本地副本

## 🔗 相关工具

### Markdown编辑工具
1. **Typora**：优秀的Markdown编辑器
2. **VS Code** + Markdown插件
3. **Obsidian**：支持本地图片管理
4. **Joplin**：开源笔记应用

### 图片处理工具
1. **ImageOptim**：图片压缩优化
2. **TinyPNG**：在线图片压缩
3. **ExifTool**：图片元数据处理

## 📖 学习资源

### SM.MS文档
- [SM.MS API文档](https://doc.sm.ms/)
- [SM.MS GitHub](https://github.com/smmsapp)

### Base64编码
- [Base64规范](https://datatracker.ietf.org/doc/html/rfc4648)
- [Data URI方案](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/Data_URIs)

### Python图像处理
- [Pillow文档](https://pillow.readthedocs.io/)
- [Requests文档](https://requests.readthedocs.io/)

## 🚧 限制说明

### 技术限制
1. **文件大小**：SM.MS限制5MB/张
2. **格式限制**：不支持所有图片格式
3. **速率限制**：免费用户10张/小时
4. **网络依赖**：需要稳定的网络连接

### 功能限制
1. **不支持视频**：仅限静态图片
2. **不支持动画**：GIF动画可能有问题
3. **不支持PDF**：无法处理PDF嵌入
4. **不支持CSS背景**：部分CSS格式无法识别

## 🔮 未来规划

### 计划功能
1. [ ] 多图床支持（Imgur、GitHub等）
2. [ ] 图片压缩和优化
3. [ ] 批量重命名和整理
4. [ ] CLI命令行版本
5. [ ] 图片水印添加
6. [ ] 自动备份到本地

### 欢迎贡献
- 报告Bug
- 提交功能请求
- 改进代码质量
- 翻译界面
- 编写文档

## 📄 许可证

MIT License - 详见LICENSE文件

## 🤝 支持与反馈

如有问题或建议：
1. 查看GitHub Issues
2. 提交新的Issue
3. 邮件联系开发者


> **提示**：在处理大量重要文档前，建议先在小文件上测试，确保配置正确。
