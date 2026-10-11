import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/data/api_auth_repository.dart';
import 'package:tennis_ai/features/auth/domain/user.dart';

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => ApiAuthRepository(ref.watch(apiClientProvider)),
);

final authControllerProvider = AsyncNotifierProvider<AuthController, AppUser?>(
  AuthController.new,
  retry: (count, error) => null,
);

class AuthController extends AsyncNotifier<AppUser?> {
  @override
  Future<AppUser?> build() async {
    final subscription = ref.watch(apiClientProvider).expired.listen((_) {
      state = const AsyncData(null);
    });
    ref.onDispose(subscription.cancel);
    return ref.watch(authRepositoryProvider).restore();
  }

  Future<void> authenticate({
    required String email,
    required String password,
    String? name,
  }) async {
    final repository = ref.read(authRepositoryProvider);
    final user = name == null
        ? await repository.login(email.trim(), password)
        : await repository.register(email.trim(), password, name.trim());
    state = AsyncData(user);
  }

  Future<void> updateName(String name) async {
    state = AsyncData(
      await ref.read(authRepositoryProvider).updateName(name.trim()),
    );
  }

  Future<void> changePassword(
    String currentPassword,
    String newPassword,
  ) async {
    await ref
        .read(authRepositoryProvider)
        .changePassword(currentPassword, newPassword);
    state = const AsyncData(null);
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(null);
  }

  Future<void> clearLocalSession() async {
    await ref.read(authRepositoryProvider).clearLocalSession();
    state = const AsyncData(null);
  }
}
