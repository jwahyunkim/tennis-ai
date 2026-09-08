import 'dart:io';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

class NativeVideoPicker implements VideoPicker {
  @override
  Future<SelectedVideo?> pick() async {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: ['mp4', 'mov'],
    );
    if (file == null) return null;
    return SelectedVideo(
      name: file.name,
      size: await file.length(),
      openRead: file.readAsByteStream,
    );
  }
}

class _LocalModelFile implements ModelFile {
  _LocalModelFile(this.directory, this.file);
  final Directory directory;
  final File file;
  @override
  String get uri => file.uri.toString();
  @override
  Future<void> dispose() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  }
}

class ApiVideoRepository implements VideoRepository {
  ApiVideoRepository(this._api);
  final ApiClient _api;

  @override
  Future<ServerCapabilities> capabilities() async {
    final response = await _api.perform(
      () => _api.dio.get<Map<String, dynamic>>('/capabilities'),
    );
    final json = response.data!;
    return ServerCapabilities(
      bodyReconstruction: json['body_reconstruction'] as bool,
      maxUploadBytes: json['max_upload_bytes'] as int,
      maxVideoSeconds: (json['max_video_seconds'] as num).toDouble(),
    );
  }

  @override
  Future<VideoPage> list({int offset = 0, int limit = 20}) async {
    final response = await _api.perform(
      () => _api.dio.get<Map<String, dynamic>>(
        '/videos',
        queryParameters: {'limit': limit, 'offset': offset},
      ),
    );
    final json = response.data!;
    return VideoPage(
      items: (json['items'] as List)
          .map((item) => TennisVideo.fromJson(item as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int,
      offset: json['offset'] as int,
    );
  }

  @override
  Future<TennisVideo> get(String id) async {
    final response = await _api.perform(
      () => _api.dio.get<Map<String, dynamic>>('/videos/$id'),
    );
    return TennisVideo.fromJson(response.data!);
  }

  @override
  Future<TennisVideo> upload(
    SelectedVideo file, {
    required void Function(int sent, int total) onProgress,
    required UploadCancellation cancellation,
  }) async {
    final cancelToken = CancelToken();
    if (cancellation.isCancelled) cancelToken.cancel();
    cancellation.cancelled.then((_) => cancelToken.cancel());
    final extension = file.name.split('.').last.toLowerCase();
    final contentType = switch (extension) {
      'mp4' => 'video/mp4',
      'mov' => 'video/quicktime',
      _ => throw const AppException(
        'unsupported_video',
        'MP4 또는 MOV 영상을 선택해 주세요.',
      ),
    };
    final body = FormData.fromMap({
      'file': MultipartFile.fromStream(
        file.openRead,
        file.size,
        filename: file.name,
        contentType: DioMediaType.parse(contentType),
      ),
    });
    final response = await _api.perform(
      () => _api.dio.post<Map<String, dynamic>>(
        '/videos',
        data: body,
        cancelToken: cancelToken,
        onSendProgress: onProgress,
      ),
    );
    return TennisVideo.fromJson(response.data!);
  }

  @override
  Future<void> delete(String id) => _api.perform(() async {
    await _api.dio.delete<void>('/videos/$id');
  });

  @override
  Future<void> createJob(String videoId) => _api.perform(() async {
    await _api.dio.post<void>('/videos/$videoId/jobs');
  });

  @override
  Future<void> cancelJob(String jobId) => _api.perform(() async {
    await _api.dio.post<void>('/jobs/$jobId/cancel');
  });

  @override
  Future<PlaybackSource> playback(String videoId) async => PlaybackSource(
    uri: _api.mediaUri('/api/v1/videos/$videoId/content'),
    headers: await _api.authorizationHeaders(),
  );

  @override
  Future<ModelFile> downloadModel(
    BodyModel model,
    UploadCancellation cancellation,
  ) async {
    if (model.format != 'glb') {
      throw const AppException('model_format', '지원하지 않는 3D 모델 형식입니다.');
    }
    final url = _api.mediaUri(model.downloadPath);
    final token = CancelToken();
    if (cancellation.isCancelled) token.cancel();
    cancellation.cancelled.then((_) => token.cancel());
    final directory = await (await getTemporaryDirectory()).createTemp(
      'tennis_model_',
    );
    final file = File('${directory.path}/model.glb');
    final result = _LocalModelFile(directory, file);
    try {
      await _api.perform(
        () => _api.dio.download(url.toString(), file.path, cancelToken: token),
      );
      if (cancellation.isCancelled) {
        throw const AppException('cancelled', '결과 보기를 취소했습니다.');
      }
      return result;
    } catch (_) {
      await result.dispose();
      rethrow;
    }
  }
}
