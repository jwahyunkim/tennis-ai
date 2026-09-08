import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';
import 'package:tennis_ai/features/videos/presentation/model_result_view.dart';
import 'package:tennis_ai/features/videos/presentation/original_video_player.dart';
import 'package:tennis_ai/features/videos/presentation/video_labels.dart';

class VideoDetailScreen extends ConsumerStatefulWidget {
  const VideoDetailScreen({required this.videoId, super.key});
  final String videoId;
  @override
  ConsumerState<VideoDetailScreen> createState() => _VideoDetailScreenState();
}

class _VideoDetailScreenState extends ConsumerState<VideoDetailScreen> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
    } catch (error) {
      if (mounted) showAppError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(TennisVideo video) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('영상을 삭제할까요?'),
        content: const Text('원본 영상과 관련 작업, 3D 결과가 함께 삭제됩니다. 되돌릴 수 없습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('돌아가기'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _run(() async {
      await ref.read(videoActionsProvider).delete(video.id);
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(videoDetailProvider(widget.videoId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('영상 상세'),
        actions: [
          IconButton(
            tooltip: '새로고침',
            onPressed: _busy
                ? null
                : () => ref.invalidate(videoDetailProvider(widget.videoId)),
            icon: const Icon(Icons.refresh),
          ),
          if (detail.value != null)
            IconButton(
              tooltip: '영상 삭제',
              onPressed: _busy ? null : () => _delete(detail.value!),
              icon: const Icon(Icons.delete_outline),
            ),
        ],
      ),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, stack) => ErrorFeedback(
          error: error,
          onRetry: () => ref.invalidate(videoDetailProvider(widget.videoId)),
        ),
        data: (video) => ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(video.filename, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              '${formatDate(video.createdAt)} · ${formatBytes(video.sizeBytes)}'
              '${video.durationSeconds == null ? '' : ' · ${video.durationSeconds!.toStringAsFixed(1)}초'}'
              '${video.width == null ? '' : ' · ${video.width}×${video.height}'}',
            ),
            const SizedBox(height: 20),
            OriginalVideoPlayer(videoId: video.id),
            const SizedBox(height: 24),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      videoStatusLabel(video),
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (video.job?.isRunning == true) ...[
                      const SizedBox(height: 12),
                      const LinearProgressIndicator(),
                    ],
                    if (video.job?.status == 'awaiting_model') ...[
                      const SizedBox(height: 8),
                      const Text(
                        '영상이 준비되었습니다. 3D 모델 생성 기능이 연결되면 분석을 진행할 수 있습니다.',
                      ),
                    ],
                    if (video.job?.status == 'failed') ...[
                      const SizedBox(height: 8),
                      Text(jobErrorLabel(video.job?.errorCode)),
                    ],
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: [
                        if (video.job == null || video.job!.canRetry)
                          OutlinedButton(
                            onPressed: _busy
                                ? null
                                : () => _run(
                                    () => ref
                                        .read(videoActionsProvider)
                                        .retry(video.id),
                                  ),
                            child: Text(
                              video.job == null ? '영상 확인 시작' : '다시 시도',
                            ),
                          ),
                        if (video.job?.canCancel == true)
                          TextButton(
                            onPressed: _busy
                                ? null
                                : () => _run(
                                    () => ref
                                        .read(videoActionsProvider)
                                        .cancel(video),
                                  ),
                            child: const Text('작업 취소'),
                          ),
                      ],
                    ),
                    if (_busy) const LinearProgressIndicator(),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text('나의 3D 모델', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            if (video.model == null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    children: [
                      Icon(
                        Icons.accessibility_new,
                        size: 48,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        '아직 3D 모델이 생성되지 않았습니다.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        '분석이 완료되면 신체 형태와 움직임을 3D로 살펴볼 수 있습니다.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              )
            else
              ModelResultView(model: video.model!),
          ],
        ),
      ),
    );
  }
}
