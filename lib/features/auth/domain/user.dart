class AppUser {
  const AppUser({
    required this.id,
    required this.email,
    required this.displayName,
  });

  final String id;
  final String email;
  final String displayName;

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'] as String,
    email: json['email'] as String,
    displayName: json['display_name'] as String,
  );
}

abstract interface class AuthRepository {
  Future<AppUser?> restore();
  Future<AppUser> login(String email, String password);
  Future<AppUser> register(String email, String password, String name);
  Future<AppUser> updateName(String name);
  Future<void> changePassword(String currentPassword, String newPassword);
  Future<void> logout();
  Future<void> clearLocalSession();
}
