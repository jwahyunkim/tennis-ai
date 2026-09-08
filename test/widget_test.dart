import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tennis_ai/app/tennis_ai_app.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';

import 'fakes.dart';

void main() {
  Future<void> mount(
    WidgetTester tester,
    FakeAuthRepository auth,
    FakeVideoRepository videos,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
          authRepositoryProvider.overrideWithValue(auth),
          videoRepositoryProvider.overrideWithValue(videos),
          videoPickerProvider.overrideWithValue(FakeVideoPicker()),
        ],
        child: const TennisAiApp(),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('signed out users see login and invalid inputs stay local', (
    tester,
  ) async {
    final auth = FakeAuthRepository();
    await mount(tester, auth, FakeVideoRepository());
    expect(find.text('Tennis AI'), findsOneWidget);
    expect(find.text('로그인'), findsNWidgets(2));
    await tester.tap(find.widgetWithText(FilledButton, '로그인'));
    await tester.pumpAndSettle();
    expect(find.text('올바른 이메일을 입력해 주세요.'), findsOneWidget);
    expect(auth.lastEmail, isNull);
  });

  testWidgets('login opens empty library with honest unavailable 3D state', (
    tester,
  ) async {
    final auth = FakeAuthRepository();
    await mount(tester, auth, FakeVideoRepository());
    await tester.enterText(
      find.byType(TextFormField).at(0),
      'player@example.com',
    );
    await tester.enterText(find.byType(TextFormField).at(1), 'strong-password');
    await tester.tap(find.widgetWithText(FilledButton, '로그인'));
    await tester.pumpAndSettle();
    expect(find.text('아직 올린 영상이 없습니다'), findsOneWidget);
    expect(find.textContaining('3D 모델 생성 기능은 준비 중'), findsOneWidget);
    expect(auth.lastEmail, 'player@example.com');
  });

  testWidgets('registration enforces password minimum before API request', (
    tester,
  ) async {
    final auth = FakeAuthRepository();
    await mount(tester, auth, FakeVideoRepository());
    await tester.tap(find.text('처음이신가요? 회원가입'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).at(0), '선수');
    await tester.enterText(
      find.byType(TextFormField).at(1),
      'player@example.com',
    );
    await tester.enterText(find.byType(TextFormField).at(2), 'short');
    await tester.ensureVisible(find.widgetWithText(FilledButton, '가입하고 시작하기'));
    await tester.tap(find.widgetWithText(FilledButton, '가입하고 시작하기'));
    await tester.pumpAndSettle();
    expect(find.text('비밀번호는 10~128자로 입력해 주세요.'), findsOneWidget);
    expect(auth.registeredName, isNull);
  });

  testWidgets('upload refreshes the video library', (tester) async {
    final videos = FakeVideoRepository();
    await mount(tester, FakeAuthRepository(user: testUser), videos);
    await tester.tap(find.text('영상 올리기'));
    await tester.pumpAndSettle();
    expect(videos.uploads, 1);
    expect(find.text('영상을 올렸습니다.'), findsOneWidget);
    expect(find.text('아직 올린 영상이 없습니다'), findsNothing);
    expect(find.text('forehand.mp4'), findsNWidgets(2));
  });

  testWidgets('library error can recover with retry', (tester) async {
    final videos = FakeVideoRepository()
      ..listError = const AppException('network', '연결 오류');
    await mount(tester, FakeAuthRepository(user: testUser), videos);
    expect(find.text('연결 오류'), findsOneWidget);
    videos.listError = null;
    await tester.tap(find.text('다시 시도'));
    await tester.pumpAndSettle();
    expect(find.text('아직 올린 영상이 없습니다'), findsOneWidget);
  });

  testWidgets('detail renders no fabricated 3D model and confirms deletion', (
    tester,
  ) async {
    final videos = FakeVideoRepository()..videos = [sampleVideo()];
    await mount(tester, FakeAuthRepository(user: testUser), videos);
    await tester.tap(find.text('forehand.mp4'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('아직 3D 모델이 생성되지 않았습니다.'), 250);
    expect(find.text('아직 3D 모델이 생성되지 않았습니다.'), findsOneWidget);
    await tester.tap(find.byTooltip('영상 삭제'));
    await tester.pumpAndSettle();
    expect(videos.videos, hasLength(1));
    await tester.tap(find.widgetWithText(FilledButton, '삭제'));
    await tester.pumpAndSettle();
    expect(videos.videos, isEmpty);
    expect(find.text('아직 올린 영상이 없습니다'), findsOneWidget);
  });

  testWidgets('logout removes private routes and returns to login', (
    tester,
  ) async {
    await mount(
      tester,
      FakeAuthRepository(user: testUser),
      FakeVideoRepository(),
    );
    await tester.tap(find.byTooltip('내 계정'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('로그아웃'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('로그아웃'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, '로그인'), findsOneWidget);
    expect(find.text('내 계정'), findsNothing);
  });
}
