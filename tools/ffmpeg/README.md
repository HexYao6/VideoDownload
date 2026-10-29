# ffmpeg 存放目录

把 `ffmpeg` 与 `ffprobe` 两个可执行文件放在这个目录下即可，程序会优先使用这里的版本
（见项目根目录 `config.json` 的 `ffmpeg.dir`）。

```
tools/ffmpeg/
├── ffmpeg
└── ffprobe
```

查找顺序：

1. `config.json` 里 `ffmpeg.path` 指定的文件（留空则跳过）；
2. 本目录下的 `ffmpeg`；
3. 系统 `PATH` 里的 `ffmpeg`。

可执行文件体积较大（约 50MB/个），已加入 `.gitignore`，不会提交到仓库。

## 从哪里获取

- Linux (arm64)：<https://johnvansickle.com/ffmpeg/> 提供静态编译版本
- Linux (x86_64)：同样从上述站点下载 `ffmpeg-release-amd64-static.tar.xz`
- macOS：`brew install ffmpeg` 后把 `$(brew --prefix)/bin/ffmpeg` 复制过来
- Windows：<https://www.gyan.dev/ffmpeg/builds/> 下载后放进本目录

## 验证

```bash
./tools/ffmpeg/ffmpeg -version
```
