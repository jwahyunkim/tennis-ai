import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';
import 'package:tennis_ai/features/videos/data/api_video_repository.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

final videoRepositoryProvider = Provider<VideoRepository>(
  (ref) => ApiVideoRepository(ref.watch(apiClientProvider)),
);
final videoPickerProvider = Provider<VideoPicker>((ref) => NativeVideoPicker());
final capabilitiesProvider = FutureProvider<ServerCapabilities>(
  (ref) => ref.watch(videoRepositoryProvider).capabilities(),
  retry: (count, error) => null,
);

final videoLibraryProvider =
    AsyncNotifierProvider.autoDispose<VideoLibraryController, VideoPage>(
      VideoLibraryController.new,
      retry: (count, error) => null,
    );

class VideoLibraryController extends AsyncNotifier<VideoPage> {
  bool _loadingMore = false;

  @override
  Future<VideoPage> build() async {
    ref.watch(authControllerProvider.select((auth) => auth.value?.id));
    return ref.watch(videoRepositoryProvider).list();
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }

  Future<void> loadMore() async {
    final page = state.value;
    if (_loadingMore || page == null || !page.hasMore) return;
    _loadingMore = true;
    try {
      final next = await ref
          .read(videoRepositoryProvider)
          .list(offset: page.nextOffset);
      if (!ref.mounted || state.value != page) return;
      final items = {
        for (final item in [...page.items, ...next.items]) item.id: item,
      };
      state = AsyncData(
        VideoPage(
          items: items.values.toList(),
          total: next.total,
          offset: 0,
          nextOffset: next.nextOffset,
        ),
      );
    } finally {
      _loadingMore = false;
    }
  }
}

final videoDetailProvider = FutureProvider.autoDispose
    .family<TennisVideo, String>((ref, id) async {
      final video = await ref.watch(videoRepositoryProvider).get(id);
      if (ref.mounted && video.job?.isRunning == true) {
        final timer = Timer(const Duration(seconds: 3), ref.invalidateSelf);
        ref.onDispose(timer.cancel);
      }
      return video;
    }, retry: (count, error) => null);

final videoPlaybackProvider = FutureProvider.autoDispose
    .family<PlaybackSource, String>(
      (ref, id) => ref.watch(videoRepositoryProvider).playback(id),
      retry: (count, error) => null,
    );

final modelFileProvider = FutureProvider.autoDispose
    .family<ModelFile, BodyModel>((ref, model) async {
      final cancellation = UploadCancellation();
      ModelFile? file;
      ref.onDispose(() {
        cancellation.cancel();
        if (file != null) unawaited(file.dispose());
      });
      file = await ref
          .watch(videoRepositoryProvider)
          .downloadModel(model, cancellation);
      if (!ref.mounted) {
        await file.dispose();
        throw const AppException('cancelled', '결과 보기를 종료했습니다.');
      }
      return file;
    }, retry: (count, error) => null);

enum UploadPhase { idle, selecting, uploading, completed, failed, cancelled }

class UploadState {
  const UploadState({
    this.phase = UploadPhase.idle,
    this.progress = 0,
    this.filename,
    this.error,
    this.videoId,
  });
  final UploadPhase phase;
  final double progress;
  final String? filename;
  final String? error;
  final String? videoId;
  bool get isBusy =>
      phase == UploadPhase.selecting || phase == UploadPhase.uploading;
}

final uploadControllerProvider =
    NotifierProvider.autoDispose<UploadController, UploadState>(
      UploadController.new,
    );

class UploadController extends Notifier<UploadState> {
  UploadCancellation? _cancellation;

  @override
  UploadState build() {
    ref.onDispose(() => _cancellation?.cancel());
    return const UploadState();
  }

  Future<void> pickAndUpload() async {
    if (state.isBusy) return;
    state = const UploadState(phase: UploadPhase.selecting);
    try {
      final capabilities = await ref.read(capabilitiesProvider.future);
      if (!ref.mounted) return;
      final file = await ref.read(videoPickerProvider).pick();
      if (!ref.mounted) return;
      if (file == null) {
        state = const UploadState();
        return;
      }
      if (file.size <= 0 || file.size > capabilities.maxUploadBytes) {
        throw AppException(
          'upload_size',
          '영상은 0바이트보다 크고 ${(capabilities.maxUploadBytes / 1024 / 1024).floor()}MB 이하여야 합니다.',
        );
      }
      _cancellation = UploadCancellation();
      state = UploadState(phase: UploadPhase.uploading, filename: file.name);
      final video = await ref
          .read(videoRepositoryProvider)
          .upload(
            file,
            cancellation: _cancellation!,
            onProgress: (sent, total) {
              if (ref.mounted && state.phase == UploadPhase.uploading) {
                state = UploadState(
                  phase: UploadPhase.uploading,
                  filename: file.name,
                  progress: total > 0 ? (sent / total).clamp(0, 1) : 0,
                );
              }
            },
          );
      if (!ref.mounted) return;
      state = UploadState(
        phase: UploadPhase.completed,
        filename: file.name,
        videoId: video.id,
        progress: 1,
      );
      ref.invalidate(videoLibraryProvider);
    } catch (error) {
      if (!ref.mounted) return;
      final cancelled =
          _cancellation?.isCancelled == true ||
          (error is AppException && error.code == 'cancelled');
      state = UploadState(
        phase: cancelled ? UploadPhase.cancelled : UploadPhase.failed,
        error: cancelled ? null : friendlyError(error),
      );
      // The server may have accepted the file just before the connection was cancelled.
      ref.invalidate(videoLibraryProvider);
    } finally {
      _cancellation = null;
    }
  }

  void cancel() => _cancellation?.cancel();
  void dismiss() {
    if (!state.isBusy) state = const UploadState();
  }
}

final videoActionsProvider = Provider<VideoActions>((ref) => VideoActions(ref));

class VideoActions {
  VideoActions(this._ref);
  final Ref _ref;

  Future<void> delete(String id) async {
    await _ref.read(videoRepositoryProvider).delete(id);
    _ref.invalidate(videoLibraryProvider);
  }

  Future<void> retry(String id) async {
    await _ref.read(videoRepositoryProvider).createJob(id);
    _ref.invalidate(videoDetailProvider(id));
    _ref.invalidate(videoLibraryProvider);
  }

  Future<void> cancel(TennisVideo video) async {
    await _ref.read(videoRepositoryProvider).cancelJob(video.job!.id);
    _ref.invalidate(videoDetailProvider(video.id));
    _ref.invalidate(videoLibraryProvider);
  }
}
