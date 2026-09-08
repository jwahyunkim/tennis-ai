import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';
import 'package:tennis_ai/features/auth/presentation/auth_screen.dart';
import 'package:tennis_ai/features/home/presentation/home_screen.dart';

class TennisAiApp extends StatelessWidget {
  const TennisAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Tennis AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2E7D32)),
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
        ),
      ),
      home: const _SessionGate(),
    );
  }
}

class _SessionGate extends ConsumerWidget {
  const _SessionGate();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(authControllerProvider);
    return session.when(
      loading: () =>
          const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (error, stack) => Scaffold(
        body: SafeArea(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ErrorFeedback(
                error: error,
                onRetry: () => ref.invalidate(authControllerProvider),
              ),
              TextButton(
                onPressed: () async {
                  try {
                    await ref
                        .read(authControllerProvider.notifier)
                        .clearLocalSession();
                  } catch (error) {
                    if (context.mounted) showAppError(context, error);
                  }
                },
                child: const Text('이 기기의 로그인 정보 지우기'),
              ),
            ],
          ),
        ),
      ),
      data: (user) {
        if (user == null) return const AuthScreen();
        // Replacing this navigator drops private routes when a session ends.
        return _AuthenticatedNavigator(key: ValueKey(user.id));
      },
    );
  }
}

class _AuthenticatedNavigator extends StatefulWidget {
  const _AuthenticatedNavigator({super.key});

  @override
  State<_AuthenticatedNavigator> createState() =>
      _AuthenticatedNavigatorState();
}

class _AuthenticatedNavigatorState extends State<_AuthenticatedNavigator> {
  final _navigatorKey = GlobalKey<NavigatorState>();

  @override
  Widget build(BuildContext context) => NavigatorPopHandler<void>(
    onPopWithResult: (_) => _navigatorKey.currentState!.pop(),
    child: Navigator(
      key: _navigatorKey,
      onGenerateRoute: (settings) => MaterialPageRoute<void>(
        settings: settings,
        builder: (_) => const HomeScreen(),
      ),
    ),
  );
}
