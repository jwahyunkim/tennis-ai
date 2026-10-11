import 'package:dio/dio.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/domain/user.dart';

class ApiAuthRepository implements AuthRepository {
  ApiAuthRepository(this._api);
  final ApiClient _api;

  @override
  Future<AppUser?> restore() async {
    if (await _api.tokenStore.read() == null) return null;
    try {
      final response = await _api.perform(
        () => _api.dio.get<Map<String, dynamic>>('/auth/me'),
      );
      return AppUser.fromJson(response.data!);
    } on AppException catch (error) {
      if (error.code == 'unauthorized') return null;
      rethrow;
    }
  }

  Future<AppUser> _authenticate(String path, Map<String, dynamic> data) async {
    final response = await _api.perform(
      () => _api.dio.post<Map<String, dynamic>>(
        path,
        data: data,
        options: Options(extra: {'public': true}),
      ),
    );
    final body = response.data!;
    final user = AppUser.fromJson(body['user'] as Map<String, dynamic>);
    await _api.tokenStore.write(body['access_token'] as String);
    return user;
  }

  @override
  Future<AppUser> login(String email, String password) =>
      _authenticate('/auth/login', {'email': email, 'password': password});

  @override
  Future<AppUser> register(String email, String password, String name) =>
      _authenticate('/auth/register', {
        'email': email,
        'password': password,
        'display_name': name,
      });

  @override
  Future<AppUser> updateName(String name) async {
    final response = await _api.perform(
      () => _api.dio.patch<Map<String, dynamic>>(
        '/auth/me',
        data: {'display_name': name},
      ),
    );
    return AppUser.fromJson(response.data!);
  }

  @override
  Future<void> changePassword(
    String currentPassword,
    String newPassword,
  ) async {
    await _api.perform(
      () => _api.dio.post<void>(
        '/auth/password',
        data: {
          'current_password': currentPassword,
          'new_password': newPassword,
        },
        options: Options(extra: {'keepSessionOn401': true}),
      ),
    );
    await clearLocalSession();
  }

  @override
  Future<void> logout() async {
    // Keep a usable session when revocation fails so the user can retry.
    await _api.perform(() => _api.dio.post<void>('/auth/logout'));
    await clearLocalSession();
  }

  @override
  Future<void> clearLocalSession() => _api.tokenStore.clear();
}
