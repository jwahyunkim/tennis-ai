import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});
  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _nameForm = GlobalKey<FormState>();
  final _passwordForm = GlobalKey<FormState>();
  late final _name = TextEditingController(
    text: ref.read(authControllerProvider).value?.displayName,
  );
  final _currentPassword = TextEditingController();
  final _newPassword = TextEditingController();
  final _confirmPassword = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _currentPassword.dispose();
    _newPassword.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action, {String? success}) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (mounted && success != null) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(success)));
      }
    } catch (error) {
      if (mounted) showAppError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).value;
    final auth = ref.read(authControllerProvider.notifier);
    return Scaffold(
      appBar: AppBar(title: const Text('내 계정')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            user?.email ?? '',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 24),
          Form(
            key: _nameForm,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _name,
                  enabled: !_busy,
                  maxLength: 80,
                  decoration: const InputDecoration(labelText: '이름'),
                  validator: (value) => value == null || value.trim().isEmpty
                      ? '이름을 입력해 주세요.'
                      : null,
                ),
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () {
                          if (_nameForm.currentState!.validate()) {
                            _run(
                              () => auth.updateName(_name.text),
                              success: '이름을 변경했습니다.',
                            );
                          }
                        },
                  child: const Text('이름 저장'),
                ),
              ],
            ),
          ),
          const Divider(height: 48),
          Text('비밀번호 변경', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const Text('변경하면 모든 기기에서 로그아웃됩니다.'),
          const SizedBox(height: 16),
          Form(
            key: _passwordForm,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _currentPassword,
                  enabled: !_busy,
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: const InputDecoration(labelText: '현재 비밀번호'),
                  validator: (value) => value == null || value.isEmpty
                      ? '현재 비밀번호를 입력해 주세요.'
                      : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _newPassword,
                  enabled: !_busy,
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: const InputDecoration(
                    labelText: '새 비밀번호',
                    helperText: '10~128자',
                  ),
                  validator: (value) {
                    if (value == null ||
                        value.length < 10 ||
                        value.length > 128) {
                      return '비밀번호는 10~128자로 입력해 주세요.';
                    }
                    if (value == _currentPassword.text) {
                      return '현재 비밀번호와 다르게 입력해 주세요.';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _confirmPassword,
                  enabled: !_busy,
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: const InputDecoration(labelText: '새 비밀번호 확인'),
                  validator: (value) =>
                      value != _newPassword.text ? '새 비밀번호가 일치하지 않습니다.' : null,
                ),
                const SizedBox(height: 16),
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () {
                          if (_passwordForm.currentState!.validate()) {
                            _run(
                              () => auth.changePassword(
                                _currentPassword.text,
                                _newPassword.text,
                              ),
                            );
                          }
                        },
                  child: const Text('비밀번호 변경'),
                ),
              ],
            ),
          ),
          const Divider(height: 48),
          FilledButton.tonal(
            onPressed: _busy ? null : () => _run(auth.logout),
            child: const Text('로그아웃'),
          ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
        ],
      ),
    );
  }
}
