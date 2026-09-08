import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';
import 'package:tennis_ai/features/auth/presentation/profile_screen.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';
import 'package:tennis_ai/features/videos/presentation/video_detail_screen.dart';
import 'package:tennis_ai/features/videos/presentation/video_labels.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _loadingMore = false;

  Future<void> _openVideo(String id) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => VideoDetailScreen(videoId: id)),
    );
    if (mounted) ref.invalidate(videoLibraryProvider);
  }

  Future<void> _loadMore() async {
    setState(() => _loadingMore = true);
    try {
      await ref.read(videoLibraryProvider.notifier).loadMore();
    } catch (error) {
      if (mounted) showAppError(context, error);
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final library = ref.watch(videoLibraryProvider);
    final capabilities = ref.watch(capabilitiesProvider);
    final upload = ref.watch(uploadControllerProvider);
    final user = ref.watch(authControllerProvider).value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tennis AI'),
        actions: [
          IconButton(
            tooltip: '새로고침',
            onPressed: () => ref.invalidate(videoLibraryProvider),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: '내 계정',
            onPressed: upload.isBusy
                ? null
                : () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const ProfileScreen(),
                    ),
                  ),
            icon: const Icon(Icons.person_outline),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: upload.isBusy
            ? null
            : () => ref.read(uploadControllerProvider.notifier).pickAndUpload(),
        icon: const Icon(Icons.add),
        label: const Text('영상 올리기'),
      ),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${user?.displayName ?? ''}님의 영상',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  capabilities.when(
                    loading: () => const Text('영상 업로드 조건을 확인하고 있습니다.'),
                    error: (error, stack) => Row(
                      children: [
                        const Expanded(child: Text('업로드 조건을 불러오지 못했습니다.')),
                        TextButton(
                          onPressed: () => ref.invalidate(capabilitiesProvider),
                          child: const Text('다시 시도'),
                        ),
                      ],
                    ),
                    data: (settings) => Text(
                      'MP4·MOV · 최대 ${(settings.maxUploadBytes / 1024 / 1024).floor()}MB · ${settings.maxVideoSeconds.toInt()}초',
                    ),
                  ),
                  if (capabilities.value?.bodyReconstruction == false) ...[
                    const SizedBox(height: 8),
                    const Text(
                      '지금은 영상을 보관하고 확인할 수 있습니다. 신체를 닮은 3D 모델 생성 기능은 준비 중입니다.',
                    ),
                  ],
                ],
              ),
            ),
            if (upload.phase != UploadPhase.idle)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: _UploadStatus(state: upload, onOpen: _openVideo),
              ),
            Expanded(
              child: library.when(
                skipLoadingOnRefresh: false,
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (error, stack) => ErrorFeedback(
                  error: error,
                  onRetry: () => ref.invalidate(videoLibraryProvider),
                ),
                data: (page) => RefreshIndicator(
                  onRefresh: () async {
                    try {
                      await ref.read(videoLibraryProvider.notifier).refresh();
                    } catch (_) {
                      /* The provider renders the refresh error. */
                    }
                  },
                  child: page.items.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.all(40),
                          children: [
                            const SizedBox(height: 48),
                            Icon(
                              Icons.video_library_outlined,
                              size: 64,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            const SizedBox(height: 20),
                            Text(
                              '아직 올린 영상이 없습니다',
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              '테니스 영상을 올려 나의 움직임을 기록해 보세요.',
                              textAlign: TextAlign.center,
                            ),
                          ],
                        )
                      : ListView.separated(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 100),
                          itemCount: page.items.length + (page.hasMore ? 1 : 0),
                          separatorBuilder: (context, index) =>
                              const SizedBox(height: 8),
                          itemBuilder: (context, index) {
                            if (index == page.items.length) {
                              return OutlinedButton(
                                onPressed: _loadingMore ? null : _loadMore,
                                child: Text(_loadingMore ? '불러오는 중…' : '더 보기'),
                              );
                            }
                            final video = page.items[index];
                            return Card(
                              child: ListTile(
                                contentPadding: const EdgeInsets.all(16),
                                leading: const Icon(
                                  Icons.play_circle_outline,
                                  size: 36,
                                ),
                                title: Text(
                                  video.filename,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: Padding(
                                  padding: const EdgeInsets.only(top: 6),
                                  child: Text(
                                    '${formatDate(video.createdAt)} · ${formatBytes(video.sizeBytes)}\n${videoStatusLabel(video)}',
                                  ),
                                ),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => _openVideo(video.id),
                              ),
                            );
                          },
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UploadStatus extends ConsumerWidget {
  const _UploadStatus({required this.state, required this.onOpen});
  final UploadState state;
  final Future<void> Function(String id) onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(uploadControllerProvider.notifier);
    final label = switch (state.phase) {
      UploadPhase.idle => '',
      UploadPhase.selecting => '영상 선택 준비 중…',
      UploadPhase.uploading =>
        state.progress >= 1
            ? '업로드를 마무리하고 있습니다…'
            : '업로드 ${(state.progress * 100).floor()}%',
      UploadPhase.completed => '영상을 올렸습니다.',
      UploadPhase.failed => state.error ?? '업로드하지 못했습니다.',
      UploadPhase.cancelled => '업로드를 취소했습니다. 목록에서 전송 여부를 확인할 수 있습니다.',
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleSmall),
            if (state.filename != null)
              Text(
                state.filename!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            if (state.isBusy) ...[
              const SizedBox(height: 12),
              LinearProgressIndicator(
                value:
                    state.phase == UploadPhase.uploading && state.progress < 1
                    ? state.progress
                    : null,
              ),
            ],
            Wrap(
              alignment: WrapAlignment.end,
              children: [
                if (state.phase == UploadPhase.uploading)
                  TextButton(
                    onPressed: controller.cancel,
                    child: const Text('업로드 취소'),
                  ),
                if (state.videoId != null)
                  TextButton(
                    onPressed: () => onOpen(state.videoId!),
                    child: const Text('영상 보기'),
                  ),
                if (!state.isBusy)
                  TextButton(
                    onPressed: controller.dismiss,
                    child: const Text('닫기'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
