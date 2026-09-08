import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/data/api_auth_repository.dart';
import 'package:tennis_ai/features/videos/data/api_video_repository.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

import 'fakes.dart';

class RecordingAdapter implements HttpClientAdapter {
  Future<ResponseBody> Function(
    RequestOptions options,
    Stream<Uint8List>? body,
  )?
  handle;
  final requests = <RequestOptions>[];
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) {
    requests.add(options);
    return handle!(options, requestStream);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonResponse(Object? data, [int status = 200]) =>
    ResponseBody.fromString(
      jsonEncode(data),
      status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );

final userJson = {
  'id': 'user-1',
  'email': 'player@example.com',
  'display_name': '테니스 선수',
};
final videoJson = {
  'id': 'video-1',
  'filename': 'forehand.mp4',
  'content_type': 'video/mp4',
  'size_bytes': 4,
  'created_at': '2026-09-08T00:00:00Z',
  'status': 'uploaded',
  'duration_seconds': null,
  'width': null,
  'height': null,
  'job': {'id': 'job-1', 'status': 'queued', 'attempts': 0, 'error_code': null},
  'model': null,
};

void main() {
  late ApiClient api;
  late MemoryTokenStore store;
  late RecordingAdapter adapter;
  late ApiAuthRepository auth;

  setUp(() {
    store = MemoryTokenStore();
    adapter = RecordingAdapter();
    api = ApiClient(
      baseUrl: 'https://api.example.com',
      tokenStore: store,
      dio: Dio()..httpClientAdapter = adapter,
    );
    auth = ApiAuthRepository(api);
  });
  tearDown(() => api.dispose());

  test(
    'login omits old authorization and persists the returned session',
    () async {
      store.token = 'old-token';
      adapter.handle = (options, stream) async =>
          jsonResponse({'access_token': 'new-token', 'user': userJson});
      final user = await auth.login('player@example.com', 'strong-password');
      expect(user.displayName, '테니스 선수');
      expect(store.token, 'new-token');
      expect(
        adapter.requests.single.uri.toString(),
        'https://api.example.com/api/v1/auth/login',
      );
      expect(
        adapter.requests.single.headers.containsKey('Authorization'),
        isFalse,
      );
      expect(adapter.requests.single.data, {
        'email': 'player@example.com',
        'password': 'strong-password',
      });
    },
  );

  test(
    'restore authenticates with bearer header and expires rejected session',
    () async {
      store.token = 'expired-token';
      adapter.handle = (options, stream) async => jsonResponse({
        'error': {'code': 'unauthorized', 'message': 'Expired'},
      }, 401);
      final event = api.expired.first;
      expect(await auth.restore(), isNull);
      await event;
      expect(store.token, isNull);
      expect(
        adapter.requests.single.headers['Authorization'],
        'Bearer expired-token',
      );
    },
  );

  test('a delayed 401 from an old session preserves a newer session', () async {
    store.token = 'old-token';
    adapter.handle = (options, stream) async {
      store.token = 'new-token';
      return jsonResponse({
        'error': {'code': 'unauthorized', 'message': 'Expired'},
      }, 401);
    };
    expect(await auth.restore(), isNull);
    expect(store.token, 'new-token');
  });

  test(
    'network failure restoring a session preserves stored credentials',
    () async {
      store.token = 'valid-token';
      adapter.handle = (options, stream) async => throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
      );
      await expectLater(
        auth.restore(),
        throwsA(
          isA<AppException>().having((error) => error.code, 'code', 'network'),
        ),
      );
      expect(store.token, 'valid-token');
    },
  );

  test(
    'unsuccessful logout keeps token available to retry revocation',
    () async {
      store.token = 'valid-token';
      adapter.handle = (options, stream) async => jsonResponse({}, 503);
      await expectLater(auth.logout(), throwsA(isA<AppException>()));
      expect(store.token, 'valid-token');
    },
  );

  test(
    'wrong current password does not expire session and successful change clears it',
    () async {
      store.token = 'valid-token';
      adapter.handle = (options, stream) async => jsonResponse({
        'error': {'code': 'invalid_credentials'},
      }, 401);
      await expectLater(
        auth.changePassword('wrong-password', 'new-password-long'),
        throwsA(isA<AppException>()),
      );
      expect(store.token, 'valid-token');
      adapter.handle = (options, stream) async => jsonResponse(null, 204);
      await auth.changePassword('old-password-long', 'new-password-long');
      expect(store.token, isNull);
    },
  );

  test(
    'video upload streams a multipart file with filename and content type',
    () async {
      store.token = 'token';
      var streamOpened = false;
      String? uploadedBody;
      adapter.handle = (options, stream) async {
        final bytes = await stream!.fold<List<int>>(
          [],
          (all, part) => all..addAll(part),
        );
        uploadedBody = utf8.decode(bytes);
        return jsonResponse(videoJson, 201);
      };
      final file = SelectedVideo(
        name: 'forehand.mp4',
        size: 4,
        openRead: () {
          streamOpened = true;
          return Stream.value(utf8.encode('test'));
        },
      );
      final result = await ApiVideoRepository(
        api,
      ).upload(file, onProgress: (_, _) {}, cancellation: UploadCancellation());
      expect(streamOpened, isTrue);
      expect(uploadedBody, contains('name="file"; filename="forehand.mp4"'));
      expect(uploadedBody, contains('content-type: video/mp4'));
      expect(uploadedBody, contains('test'));
      expect(result.job!.status, 'queued');
      expect(result.model, isNull);
    },
  );

  test('upload cancelled before dispatch never reaches adapter', () async {
    final cancellation = UploadCancellation()..cancel();
    await expectLater(
      ApiVideoRepository(api).upload(
        SelectedVideo(
          name: 'forehand.mp4',
          size: 1,
          openRead: () => Stream.value([1]),
        ),
        onProgress: (_, _) {},
        cancellation: cancellation,
      ),
      throwsA(
        isA<AppException>().having((error) => error.code, 'code', 'cancelled'),
      ),
    );
    expect(adapter.requests, isEmpty);
  });

  test(
    'media credentials remain headers and external model URLs are rejected',
    () async {
      store.token = 'private-token';
      final source = await ApiVideoRepository(api).playback('video-1');
      expect(
        source.uri.toString(),
        'https://api.example.com/api/v1/videos/video-1/content',
      );
      expect(source.uri.hasQuery, isFalse);
      expect(source.headers['Authorization'], 'Bearer private-token');
      for (final path in [
        'https://attacker.example/model.glb',
        '//attacker.example/model.glb',
        '/api/v1/../private',
        '/api/v1/models/x?token=secret',
      ]) {
        expect(() => api.mediaUri(path), throwsA(isA<AppException>()));
      }
    },
  );

  test('release client rejects HTTP and base URLs with a path', () {
    expect(
      () => ApiClient(
        baseUrl: 'http://api.example.com',
        tokenStore: store,
        requireHttps: true,
      ),
      throwsA(isA<AppException>()),
    );
    expect(
      () => ApiClient(
        baseUrl: 'https://api.example.com/api/v1',
        tokenStore: store,
      ),
      throwsA(isA<AppException>()),
    );
  });
}
