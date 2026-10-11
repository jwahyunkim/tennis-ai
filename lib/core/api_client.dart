import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _configuredBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

final tokenStoreProvider = Provider<TokenStore>(
  (ref) => SecureTokenStore(const FlutterSecureStorage()),
);

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(
    baseUrl: _configuredBaseUrl,
    tokenStore: ref.watch(tokenStoreProvider),
    requireHttps: kReleaseMode,
  );
  ref.onDispose(client.dispose);
  return client;
});

abstract interface class TokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class SecureTokenStore implements TokenStore {
  SecureTokenStore(this._storage);

  final FlutterSecureStorage _storage;
  static const _key = 'tennis_ai_access_token';

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

class AppException implements Exception {
  const AppException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => message;
}

String friendlyError(Object error) {
  if (error is AppException) return error.message;
  return '요청을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.';
}

class ApiClient {
  ApiClient({
    required String baseUrl,
    required this.tokenStore,
    bool requireHttps = false,
    Dio? dio,
  }) : origin = Uri.parse(baseUrl.replaceAll(RegExp(r'/+$'), '')),
       dio = dio ?? Dio() {
    if (!origin.hasAuthority ||
        !['http', 'https'].contains(origin.scheme) ||
        origin.userInfo.isNotEmpty ||
        origin.path.isNotEmpty ||
        origin.hasQuery ||
        origin.hasFragment ||
        (requireHttps && origin.scheme != 'https')) {
      throw const AppException('configuration', '서버 주소 설정을 확인해 주세요.');
    }
    this.dio.options = BaseOptions(
      baseUrl: '$origin/api/v1',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(minutes: 5),
      followRedirects: false,
      headers: {'Accept': 'application/json'},
    );
    this.dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          try {
            if (options.extra['public'] != true) {
              final token = await tokenStore.read();
              if (token != null) {
                options.headers['Authorization'] = 'Bearer $token';
              }
            }
            handler.next(options);
          } catch (_) {
            handler.reject(
              DioException(
                requestOptions: options,
                error: const AppException('storage', '로그인 정보를 읽지 못했습니다.'),
              ),
            );
          }
        },
        onError: (error, handler) async {
          if (error.response?.statusCode == 401 &&
              error.requestOptions.headers['Authorization'] != null &&
              error.requestOptions.extra['keepSessionOn401'] != true) {
            // A delayed response from a previous session must not log out a new one.
            try {
              final token = await tokenStore.read();
              if (error.requestOptions.headers['Authorization'] ==
                  'Bearer $token') {
                await tokenStore.clear();
                if (!_expired.isClosed) _expired.add(null);
              }
            } catch (_) {
              // Storage failures must not leave the HTTP request unresolved.
              if (!_expired.isClosed) _expired.add(null);
            }
          }
          handler.next(error);
        },
      ),
    );
  }

  final Uri origin;
  final Dio dio;
  final TokenStore tokenStore;
  final _expired = StreamController<void>.broadcast();
  Stream<void> get expired => _expired.stream;

  Future<T> perform<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on DioException catch (error) {
      if (error.error is AppException) throw error.error!;
      if (CancelToken.isCancel(error)) {
        throw const AppException('cancelled', '업로드를 취소했습니다.');
      }
      final response = error.response;
      final body = response?.data;
      final detail = body is Map ? body['error'] : null;
      final code = detail is Map ? detail['code'] as String? : null;
      const messages = {
        'invalid_credentials': '이메일 또는 비밀번호를 확인해 주세요.',
        'email_exists': '이미 가입된 이메일입니다.',
        'account_exists': '이미 가입된 이메일입니다.',
        'email_already_registered': '이미 가입된 이메일입니다.',
        'invalid_password': '현재 비밀번호를 확인해 주세요.',
        'upload_too_large': '허용된 영상 용량을 초과했습니다.',
        'video_too_large': '허용된 영상 용량을 초과했습니다.',
        'storage_quota_exceeded': '영상 저장 한도를 초과했습니다. 기존 영상을 정리해 주세요.',
        'unsupported_video': '지원하지 않는 영상 형식입니다.',
        'invalid_video': '재생 가능한 영상 파일을 선택해 주세요.',
        'video_too_long': '허용된 영상 길이를 초과했습니다.',
        'job_active': '이미 진행 중인 작업이 있습니다.',
        'job_stopping': '이전 작업을 정리하고 있습니다. 잠시 후 다시 시도해 주세요.',
        'storage_full': '저장 공간이 부족합니다. 잠시 후 다시 시도해 주세요.',
        'quota_exceeded': '영상 저장 한도를 초과했습니다. 기존 영상을 정리해 주세요.',
      };
      if (messages.containsKey(code)) {
        throw AppException(code!, messages[code]!);
      }
      switch (response?.statusCode) {
        case 401:
          throw const AppException('unauthorized', '로그인이 필요합니다. 다시 로그인해 주세요.');
        case 403:
          throw const AppException('forbidden', '이 작업에 접근할 수 없습니다.');
        case 404:
          throw const AppException(
            'not_found',
            '영상을 찾을 수 없습니다. 목록을 새로고침해 주세요.',
          );
        case 409:
          throw AppException(
            code ?? 'conflict',
            '현재 상태에서는 요청을 처리할 수 없습니다. 새로고침해 주세요.',
          );
        case 413:
          throw const AppException('too_large', '허용된 영상 용량을 초과했습니다.');
        case 415:
          throw const AppException(
            'unsupported_video',
            'MP4 또는 MOV 영상을 선택해 주세요.',
          );
        case 422:
          throw AppException(
            code ?? 'validation',
            '입력한 내용 또는 영상 형식과 길이를 확인해 주세요.',
          );
        case 429:
          throw const AppException('rate_limit', '요청이 많습니다. 잠시 후 다시 시도해 주세요.');
        case null:
          throw const AppException(
            'network',
            '서버에 연결할 수 없습니다. 네트워크 연결을 확인해 주세요.',
          );
        default:
          throw AppException(
            code ?? 'server',
            '서버에서 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
          );
      }
    }
  }

  Uri mediaUri(String path) {
    final relative = Uri.parse(path);
    if (relative.hasScheme ||
        relative.hasAuthority ||
        !path.startsWith('/api/v1/') ||
        relative.hasQuery ||
        relative.hasFragment ||
        !relative.path.startsWith('/api/v1/') ||
        Uri.decodeComponent(path).split('/').contains('..')) {
      throw const AppException('invalid_model_path', '결과 파일 주소를 확인할 수 없습니다.');
    }
    return origin.resolve(path);
  }

  Future<Map<String, String>> authorizationHeaders() async {
    final token = await tokenStore.read();
    if (token == null) throw const AppException('unauthorized', '다시 로그인해 주세요.');
    return {'Authorization': 'Bearer $token'};
  }

  void dispose() {
    dio.close(force: true);
    unawaited(_expired.close());
  }
}
