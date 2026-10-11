import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/data/api_auth_repository.dart';
import 'package:tennis_ai/features/videos/data/api_video_repository.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

import 'fakes.dart';

// Opt in against a disposable local stack:
// TEST_API_BASE_URL=http://127.0.0.1:8000 flutter test test/api_live_test.dart
// Requires ffmpeg on PATH. The synthetic account remains; its video and session
// are removed. Never point this test at production.
void main() {
  final baseUrl = Platform.environment['TEST_API_BASE_URL'];

  test(
    'Flutter repositories complete real auth and video preparation flow',
    () async {
      final store = MemoryTokenStore();
      final api = ApiClient(baseUrl: baseUrl!, tokenStore: store);
      final auth = ApiAuthRepository(api);
      final videos = ApiVideoRepository(api);
      final directory = await Directory.systemTemp.createTemp(
        'tennis_flutter_live_',
      );
      String? videoId;
      addTearDown(() async {
        try {
          if (videoId != null && store.token != null) {
            await videos.delete(videoId);
          }
          if (store.token != null) await auth.logout();
        } finally {
          api.dispose();
          await directory.delete(recursive: true);
        }
      });

      final fixture = File('${directory.path}/forehand.mp4');
      final generated = await Process.run('ffmpeg', [
        '-hide_banner',
        '-loglevel',
        'error',
        '-f',
        'lavfi',
        '-i',
        'color=c=green:s=160x120:r=15',
        '-t',
        '1',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        fixture.path,
      ]);
      expect(
        generated.exitCode,
        0,
        reason: 'ffmpeg must create a valid MP4 fixture',
      );

      final suffix = DateTime.now().microsecondsSinceEpoch;
      final user = await auth.register(
        'flutter-live-$suffix@example.com',
        'Live-test-only-$suffix',
        '테스트 선수',
      );
      expect((await auth.restore())!.id, user.id);
      expect((await auth.updateName('영상 테스트')).displayName, '영상 테스트');
      final capabilities = await videos.capabilities();
      expect(capabilities.bodyReconstruction, isFalse);
      expect((await videos.list()).items, isEmpty);

      final uploaded = await videos.upload(
        SelectedVideo(
          name: 'forehand.mp4',
          size: await fixture.length(),
          openRead: fixture.openRead,
        ),
        onProgress: (_, _) {},
        cancellation: UploadCancellation(),
      );
      videoId = uploaded.id;
      expect(uploaded.model, isNull);
      expect((await videos.list()).items.single.id, uploaded.id);
      final ready = await _waitForPreparation(videos, uploaded.id);
      expect(ready.job!.status, 'awaiting_model');
      expect(ready.width, 160);
      expect(ready.height, 120);
      expect(ready.durationSeconds, closeTo(1, 0.2));
      expect(ready.model, isNull);

      final playback = await videos.playback(uploaded.id);
      final content = await api.perform(
        () => api.dio.get<List<int>>(
          playback.uri.toString(),
          options: Options(
            responseType: ResponseType.bytes,
            headers: {'Range': 'bytes=0-15'},
          ),
        ),
      );
      expect(content.statusCode, 206);
      expect(content.data, hasLength(16));

      await videos.cancelJob(ready.job!.id);
      expect((await videos.get(uploaded.id)).job!.status, 'cancelled');
      await videos.createJob(uploaded.id);
      expect(
        (await _waitForPreparation(videos, uploaded.id)).job!.status,
        'awaiting_model',
      );
      await videos.delete(uploaded.id);
      videoId = null;
      expect((await videos.list()).items, isEmpty);
      await auth.logout();
      expect(store.token, isNull);
    },
    skip: baseUrl == null
        ? 'Set TEST_API_BASE_URL to run against a disposable API stack.'
        : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}

Future<TennisVideo> _waitForPreparation(
  ApiVideoRepository repository,
  String id,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (true) {
    final video = await repository.get(id);
    if (video.job?.isRunning != true) return video;
    if (DateTime.now().isAfter(deadline)) {
      fail('Video preparation worker did not finish within 45 seconds.');
    }
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
}
