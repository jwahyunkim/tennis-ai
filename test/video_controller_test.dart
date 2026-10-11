import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/application/auth_controller.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';

import 'fakes.dart';

void main() {
  late ProviderContainer container;
  late FakeVideoRepository repository;
  late FakeVideoPicker picker;

  setUp(() {
    repository = FakeVideoRepository();
    picker = FakeVideoPicker();
    container = ProviderContainer(
      overrides: [
        tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
        authRepositoryProvider.overrideWithValue(
          FakeAuthRepository(user: testUser),
        ),
        videoRepositoryProvider.overrideWithValue(repository),
        videoPickerProvider.overrideWithValue(picker),
      ],
    );
  });
  tearDown(() => container.dispose());

  test(
    'load more appends results and keeps existing data if next page fails',
    () async {
      repository.videos = List.generate(
        25,
        (index) => sampleVideo(id: 'video-$index'),
      );
      final subscription = container.listen(videoLibraryProvider, (_, _) {});
      addTearDown(subscription.close);
      await container.read(authControllerProvider.future);
      final first = await container.read(videoLibraryProvider.future);
      expect(first.items, hasLength(20));
      repository.listError = const AppException('network', 'Offline');
      await expectLater(
        container.read(videoLibraryProvider.notifier).loadMore(),
        throwsA(isA<AppException>()),
      );
      expect(container.read(videoLibraryProvider).value!.items, hasLength(20));
      repository.listError = null;
      await container.read(videoLibraryProvider.notifier).loadMore();
      expect(container.read(videoLibraryProvider).value!.items, hasLength(25));
      expect(container.read(videoLibraryProvider).value!.hasMore, isFalse);
      expect(repository.offsets.last, 20);
    },
  );

  test('oversize video is rejected before upload starts', () async {
    picker.size = 2048;
    final subscription = container.listen(uploadControllerProvider, (_, _) {});
    addTearDown(subscription.close);
    await container.read(uploadControllerProvider.notifier).pickAndUpload();
    expect(container.read(uploadControllerProvider).phase, UploadPhase.failed);
    expect(repository.uploads, 0);
  });

  test(
    'cancellation propagates to in-flight upload and clears busy state',
    () async {
      repository.waitForCancellation = true;
      final subscription = container.listen(
        uploadControllerProvider,
        (_, _) {},
      );
      addTearDown(subscription.close);
      final completed = container
          .read(uploadControllerProvider.notifier)
          .pickAndUpload();
      await Future<void>.delayed(Duration.zero);
      expect(container.read(uploadControllerProvider).progress, 0.5);
      container.read(uploadControllerProvider.notifier).cancel();
      await completed;
      expect(
        container.read(uploadControllerProvider).phase,
        UploadPhase.cancelled,
      );
      expect(container.read(uploadControllerProvider).isBusy, isFalse);
    },
  );
}
