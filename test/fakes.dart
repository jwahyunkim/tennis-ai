import 'dart:async';

import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/auth/domain/user.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

const testUser = AppUser(
  id: 'user-1',
  email: 'player@example.com',
  displayName: '테니스 선수',
);

class MemoryTokenStore implements TokenStore {
  MemoryTokenStore([this.token]);
  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async {
    token = value;
  }

  @override
  Future<void> clear() async {
    token = null;
  }
}

class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({this.user});
  AppUser? user;
  Object? restoreError;
  Object? loginError;
  String? lastEmail;
  String? registeredName;
  @override
  Future<AppUser?> restore() async {
    if (restoreError != null) throw restoreError!;
    return user;
  }

  @override
  Future<AppUser> login(String email, String password) async {
    lastEmail = email;
    if (loginError != null) throw loginError!;
    return user = testUser;
  }

  @override
  Future<AppUser> register(String email, String password, String name) async {
    registeredName = name;
    return login(email, password);
  }

  @override
  Future<AppUser> updateName(String name) async =>
      user = AppUser(id: testUser.id, email: testUser.email, displayName: name);
  @override
  Future<void> changePassword(
    String currentPassword,
    String newPassword,
  ) async {
    user = null;
  }

  @override
  Future<void> logout() async {
    user = null;
  }

  @override
  Future<void> clearLocalSession() async {
    user = null;
  }
}

TennisVideo sampleVideo({
  String id = 'video-1',
  String status = 'awaiting_model',
}) => TennisVideo(
  id: id,
  filename: 'forehand.mp4',
  contentType: 'video/mp4',
  sizeBytes: 1024,
  createdAt: DateTime.utc(2026, 9, 8),
  status: 'ready',
  durationSeconds: 10,
  width: 640,
  height: 480,
  job: AnalysisJob(id: 'job-$id', status: status, attempts: 1),
);

class FakeVideoPicker implements VideoPicker {
  FakeVideoPicker({this.size = 10});
  int size;
  int calls = 0;
  @override
  Future<SelectedVideo?> pick() async {
    calls++;
    return SelectedVideo(
      name: 'forehand.mp4',
      size: size,
      openRead: () => Stream.value(List.filled(size, 1)),
    );
  }
}

class FakeVideoRepository implements VideoRepository {
  List<TennisVideo> videos = [];
  Object? listError;
  int listCalls = 0;
  final offsets = <int>[];
  int uploads = 0;
  int retries = 0;
  int cancellations = 0;
  bool waitForCancellation = false;
  @override
  Future<ServerCapabilities> capabilities() async => const ServerCapabilities(
    bodyReconstruction: false,
    maxUploadBytes: 1024,
    maxVideoSeconds: 120,
  );
  @override
  Future<VideoPage> list({int offset = 0, int limit = 20}) async {
    listCalls++;
    offsets.add(offset);
    if (listError != null) throw listError!;
    return VideoPage(
      items: videos.skip(offset).take(limit).toList(),
      total: videos.length,
      offset: offset,
    );
  }

  @override
  Future<TennisVideo> get(String id) async =>
      videos.firstWhere((video) => video.id == id);
  @override
  Future<TennisVideo> upload(
    SelectedVideo file, {
    required void Function(int sent, int total) onProgress,
    required UploadCancellation cancellation,
  }) async {
    uploads++;
    onProgress(5, 10);
    if (waitForCancellation) {
      await cancellation.cancelled;
      throw const AppException('cancelled', 'Cancelled');
    }
    final video = sampleVideo();
    videos = [...videos, video];
    onProgress(10, 10);
    return video;
  }

  @override
  Future<void> delete(String id) async {
    videos = videos.where((video) => video.id != id).toList();
  }

  @override
  Future<void> createJob(String videoId) async {
    retries++;
  }

  @override
  Future<void> cancelJob(String jobId) async {
    cancellations++;
  }

  @override
  Future<PlaybackSource> playback(String videoId) async =>
      throw const AppException('test_playback', '테스트에서는 영상을 재생하지 않습니다.');
  @override
  Future<ModelFile> downloadModel(
    BodyModel model,
    UploadCancellation cancellation,
  ) => throw UnimplementedError();
}
