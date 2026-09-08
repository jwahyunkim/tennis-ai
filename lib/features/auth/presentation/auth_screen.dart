import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key});
  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  bool _register = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(authControllerProvider.notifier)
          .authenticate(
            email: _email.text,
            password: _password.text,
            name: _register ? _name.text : null,
          );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: AutofillGroup(
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Icon(
                      Icons.sports_tennis,
                      size: 64,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Tennis AI',
                      style: Theme.of(context).textTheme.headlineLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '나의 테니스 영상을 모으고\n몸의 움직임을 이해하는 첫걸음',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 32),
                    Text(
                      _register ? '회원가입' : '로그인',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 16),
                    if (_register) ...[
                      TextFormField(
                        controller: _name,
                        enabled: !_busy,
                        maxLength: 80,
                        autofillHints: const [AutofillHints.nickname],
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(labelText: '이름'),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? '이름을 입력해 주세요.'
                            : null,
                      ),
                      const SizedBox(height: 12),
                    ],
                    TextFormField(
                      controller: _email,
                      enabled: !_busy,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      decoration: const InputDecoration(labelText: '이메일'),
                      validator: (value) =>
                          value == null ||
                              !RegExp(
                                r'^[^\s@]+@[^\s@]+\.[^\s@]+$',
                              ).hasMatch(value.trim())
                          ? '올바른 이메일을 입력해 주세요.'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _password,
                      enabled: !_busy,
                      obscureText: _obscure,
                      enableSuggestions: false,
                      autocorrect: false,
                      autofillHints: [
                        _register
                            ? AutofillHints.newPassword
                            : AutofillHints.password,
                      ],
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: '비밀번호',
                        helperText: _register ? '10~128자' : null,
                        suffixIcon: IconButton(
                          tooltip: _obscure ? '비밀번호 보기' : '비밀번호 숨기기',
                          onPressed: () => setState(() => _obscure = !_obscure),
                          icon: Icon(
                            _obscure
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return '비밀번호를 입력해 주세요.';
                        }
                        if (_register &&
                            (value.length < 10 || value.length > 128)) {
                          return '비밀번호는 10~128자로 입력해 주세요.';
                        }
                        return null;
                      },
                    ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 16),
                        child: Text(
                          _error!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(_register ? '가입하고 시작하기' : '로그인'),
                    ),
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () => setState(() {
                              _register = !_register;
                              _error = null;
                              _form.currentState?.reset();
                            }),
                      child: Text(
                        _register ? '이미 계정이 있어요 · 로그인' : '처음이신가요? 회원가입',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
