import 'dart:async';

class AnalysisJob {
  const AnalysisJob({
    required this.id,
    required this.status,
    required this.attempts,
    this.errorCode,
  });
  final String id;
  final String status;
  final int attempts;
  final String? errorCode;
  bool get isRunning => status == 'queued' || status == 'processing';
  bool get canRetry => status == 'failed' || status == 'cancelled';
  bool get canCancel => isRunning || status == 'awaiting_model';

  factory AnalysisJob.fromJson(Map<String, dynamic> json) => AnalysisJob(
    id: json['id'] as String,
    status: json['status'] as String,
    attempts: json['attempts'] as int,
    errorCode: json['error_code'] as String?,
  );
}

class BodyModel {
  const BodyModel({
    required this.id,
    required this.format,
    required this.downloadPath,
  });
  final String id;
  final String format;
  final String downloadPath;

  factory BodyModel.fromJson(Map<String, dynamic> json) => BodyModel(
    id: json['id'] as String,
    format: json['format'] as String,
    downloadPath: json['download_path'] as String,
  );
}

class TennisVideo {
  const TennisVideo({
    required this.id,
    required this.filename,
    required this.contentType,
    required this.sizeBytes,
    required this.createdAt,
    required this.status,
    this.durationSeconds,
    this.width,
    this.height,
    this.job,
    this.model,
  });
  final String id;
  final String filename;
  final String contentType;
  final int sizeBytes;
  final DateTime createdAt;
  final String status;
  final double? durationSeconds;
  final int? width;
  final int? height;
  final AnalysisJob? job;
  final BodyModel? model;

  factory TennisVideo.fromJson(Map<String, dynamic> json) => TennisVideo(
    id: json['id'] as String,
    filename: json['filename'] as String,
    contentType: json['content_type'] as String,
    sizeBytes: json['size_bytes'] as int,
    createdAt: DateTime.parse(json['created_at'] as String),
    status: json['status'] as String,
    durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
    width: json['width'] as int?,
    height: json['height'] as int?,
    job: json['job'] == null
        ? null
        : AnalysisJob.fromJson(json['job'] as Map<String, dynamic>),
    model: json['model'] == null
        ? null
        : BodyModel.fromJson(json['model'] as Map<String, dynamic>),
  );
}

class VideoPage {
  VideoPage({
    required List<TennisVideo> items,
    required this.total,
    required this.offset,
    int? nextOffset,
  }) : items = List.unmodifiable(items),
       nextOffset = nextOffset ?? offset + items.length;
  final List<TennisVideo> items;
  final int total;
  final int offset;
  final int nextOffset;
  bool get hasMore => nextOffset < total;
}

class ServerCapabilities {
  const ServerCapabilities({
    required this.bodyReconstruction,
    required this.maxUploadBytes,
    required this.maxVideoSeconds,
  });
  final bool bodyReconstruction;
  final int maxUploadBytes;
  final double maxVideoSeconds;
}

class SelectedVideo {
  const SelectedVideo({
    required this.name,
    required this.size,
    required this.openRead,
  });
  final String name;
  final int size;
  final Stream<List<int>> Function() openRead;
}

class UploadCancellation {
  final _completer = Completer<void>();
  bool get isCancelled => _completer.isCompleted;
  Future<void> get cancelled => _completer.future;
  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }
}

class PlaybackSource {
  PlaybackSource({required this.uri, required Map<String, String> headers})
    : headers = Map.unmodifiable(headers);
  final Uri uri;
  final Map<String, String> headers;
}

abstract interface class ModelFile {
  String get uri;
  Future<void> dispose();
}

abstract interface class VideoPicker {
  Future<SelectedVideo?> pick();
}

abstract interface class VideoRepository {
  Future<ServerCapabilities> capabilities();
  Future<VideoPage> list({int offset = 0, int limit = 20});
  Future<TennisVideo> get(String id);
  Future<TennisVideo> upload(
    SelectedVideo file, {
    required void Function(int sent, int total) onProgress,
    required UploadCancellation cancellation,
  });
  Future<void> delete(String id);
  Future<void> createJob(String videoId);
  Future<void> cancelJob(String jobId);
  Future<PlaybackSource> playback(String videoId);
  Future<ModelFile> downloadModel(
    BodyModel model,
    UploadCancellation cancellation,
  );
}
