"""异步 Worker 模块 / Background Worker module.

所有耗时操作通过 QThread + Worker QObject 执行，不阻塞 UI 线程。
"""

