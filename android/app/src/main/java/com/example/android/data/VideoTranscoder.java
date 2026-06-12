package com.example.android.data;

import android.content.Context;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.OptIn;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.effect.Presentation;
import androidx.media3.transformer.Composition;
import androidx.media3.transformer.DefaultEncoderFactory;
import androidx.media3.transformer.EditedMediaItem;
import androidx.media3.transformer.Effects;
import androidx.media3.transformer.ExportException;
import androidx.media3.transformer.ExportResult;
import androidx.media3.transformer.InAppMp4Muxer;
import androidx.media3.transformer.Transformer;
import androidx.media3.transformer.VideoEncoderSettings;

import java.io.File;
import java.io.IOException;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Storage Saver video transcoder — re-encodes a video to H.264, capped at
 * {@value #TARGET_HEIGHT}p and ~{@value #TARGET_VIDEO_BITRATE} bps, into a temp
 * MP4 file in {@link Context#getCacheDir()}.
 *
 * <p><b>Contract</b> (see {@code BackupTransferUseCase.prepareStream()}):
 * <ul>
 *   <li>{@link #transcode} is <b>synchronous</b> — it blocks the calling worker
 *       thread until the export completes, fails, or times out. The calling
 *       thread has no {@link android.os.Looper}; Media3 {@link Transformer}
 *       requires one, so the export runs on a private {@link HandlerThread}.</li>
 *   <li>Returns the temp {@link File} on success. The <b>caller</b> owns and
 *       deletes it (via {@code TempFileInputStream.close()}).</li>
 *   <li>Returns {@code null} when transcoding would yield no savings or on any
 *       error — the caller silently falls back to streaming the raw bytes. On
 *       every {@code null} path this class deletes its own temp file.</li>
 *   <li>Never throws.</li>
 * </ul>
 *
 * <p><b>Concurrency:</b> the backup pool runs up to 5 slots in parallel, but
 * transcoding is fully serialized through a fair static {@link Semaphore} with
 * {@value #MAX_CONCURRENT_TRANSCODES} permit: one video transcodes at a time and
 * the other slots block until it finishes. Parallel transcodes compete for the
 * device's limited hardware codec instances and multiply decoder/encoder/sample
 * queue memory — which crashed the heap with {@link OutOfMemoryError} in testing.
 */
@OptIn(markerClass = UnstableApi.class)
public final class VideoTranscoder {

    private static final String TAG = "VideoTranscoder";

    /**
     * Output height cap (long side after rotation). 720p is the Storage Saver target.
     */
    private static final int TARGET_HEIGHT = 720;

    /**
     * Requested H.264 video bitrate, in bits per second.
     */
    private static final int TARGET_VIDEO_BITRATE = 3_000_000;

    /**
     * Pre-check skip tolerance: a source whose total bitrate is already within
     * 20% of the target gains nothing from a re-encode.
     */
    private static final double SKIP_BITRATE_TOLERANCE = 1.2;

    /**
     * Transcodes are fully serialized: exactly one video runs through the codec
     * pipeline at a time. Other backup slots <b>block and wait</b> for their turn
     * (fair FIFO order) instead of falling back to raw — concurrent transcodes
     * compete for hardware codec instances and multiply decoder/encoder/queue
     * memory, which OOM-crashed the 256 MB heap.
     */
    private static final int MAX_CONCURRENT_TRANSCODES = 1;

    /**
     * Export timeout = BASE + 1s per source MB, capped at MAX.
     */
    private static final long BASE_TIMEOUT_MS = 60_000L;
    private static final long PER_MB_TIMEOUT_MS = 1_000L;
    private static final long MAX_TIMEOUT_MS = 15L * 60_000L;

    /**
     * Fair: waiting slots acquire the codec in FIFO order — no slot starves.
     */
    private static final Semaphore CODEC_SLOTS = new Semaphore(MAX_CONCURRENT_TRANSCODES, true);

    private VideoTranscoder() {
        // Static utility — no instances.
    }

    /**
     * Synchronously transcodes {@code inputUri} to a smaller H.264 MP4 temp file.
     *
     * @param context           Application context (codec + ContentResolver access).
     * @param inputUri          Source video URI (content:// or file://).
     * @param originalSizeBytes Size of the original file — used for the savings
     *                          check and the size-proportional timeout.
     * @param slotIndex         Zero-based backup slot index (logging only).
     * @return The transcoded temp file (in {@code getCacheDir()}), or {@code null}
     * if the source is already small, the result yields no savings, or any
     * error/timeout occurred. Never throws.
     */
    @Nullable
    public static File transcode(@NonNull Context context,
                                 @NonNull Uri inputUri,
                                 long originalSizeBytes,
                                 int slotIndex) {
        VideoInfo info = probe(context, inputUri);

        // ── Not a parseable video: MediaMetadataRetriever found no video track. ──
        // Extension-based selection (isTranscodableVideo) lets through files that
        // merely *look* like videos (e.g. a non-MPEG ".ts" file, corrupt files).
        // Media3's extractors would fail on these too (UnrecognizedInputFormatException),
        // so skip the codec work entirely and let the caller stream the raw bytes.
        if (info == null) {
            Log.d(TAG, "Slot " + slotIndex + ": no readable video track in "
                    + inputUri + " — skip transcode (raw fallback)");
            return null;
        }

        // ── Cheap skip: already ≤720p at (near-)target bitrate — no savings. ──
        if (info.shortSide > 0 && info.shortSide <= TARGET_HEIGHT
                && info.bitrate > 0
                && info.bitrate <= TARGET_VIDEO_BITRATE * SKIP_BITRATE_TOLERANCE) {
            Log.d(TAG, "Slot " + slotIndex + ": source already " + info.shortSide
                    + "p @ " + info.bitrate + " bps — skip transcode");
            return null;
        }

        // Wait (block) for the single codec permit — transcodes run one at a time.
        // The permit is always released within the export timeout, so this cannot
        // wait forever; stopTransfer() interrupts the pool thread, which lands in
        // the catch below and falls back to raw.
        try {
            CODEC_SLOTS.acquire();
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            Log.d(TAG, "Slot " + slotIndex + ": interrupted while waiting for codec — raw fallback");
            return null;
        }
        try {
            return runTranscode(context, inputUri, info, originalSizeBytes, slotIndex);
        } finally {
            CODEC_SLOTS.release();
        }
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Export pipeline
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * Runs a Media3 {@link Transformer} export on a dedicated {@link HandlerThread}
     * and blocks the calling thread on a {@link CountDownLatch} until completion,
     * error, or timeout.
     */
    @Nullable
    private static File runTranscode(@NonNull Context context,
                                     @NonNull Uri inputUri,
                                     @NonNull VideoInfo info,
                                     long originalSizeBytes,
                                     int slotIndex) {
        // Cap at TARGET_HEIGHT but never upscale a sub-720p source. The effect is
        // applied even when the height is unchanged: without it, an already-H.264
        // source skips re-encoding entirely and Transformer TRANSMUXES the whole
        // video track through an in-memory queue — zero savings and the path that
        // caused OutOfMemoryError in EncodedSampleExporter on long videos.
        // Forcing the effect guarantees the bounded encoder path at our bitrate.
        // (& ~1: H.264 encoders require even dimensions.)
        final int outputHeight = Math.min(TARGET_HEIGHT, info.effectiveHeight) & ~1;

        final File outputFile;
        try {
            outputFile = File.createTempFile(
                    "transcode_" + slotIndex + "_", ".mp4", context.getCacheDir());
        } catch (IOException ioe) {
            Log.w(TAG, "Slot " + slotIndex + ": cannot create temp file ("
                    + ioe.getMessage() + ") — raw fallback");
            return null;
        }

        HandlerThread handlerThread = new HandlerThread("VideoTranscoder-" + slotIndex);
        handlerThread.start();
        Handler handler = new Handler(handlerThread.getLooper());

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<Exception> error = new AtomicReference<>();
        AtomicReference<Transformer> transformerRef = new AtomicReference<>();

        try {
            handler.post(() -> {
                try {
                    Transformer transformer = new Transformer.Builder(context)
                            .setVideoMimeType(MimeTypes.VIDEO_H264)
                            // Force AAC: MKV/WebM sources carry Vorbis/Opus audio, and
                            // AAC-in-MP4 is the only combination guaranteed to play on
                            // the Windows (SyncDose) side. Already-AAC audio is
                            // transmuxed as-is, so MP4 sources pay no re-encode cost.
                            .setAudioMimeType(MimeTypes.AUDIO_AAC)
                            // Use Media3's pure-Java MP4 muxer instead of the framework
                            // MediaMuxer/MPEG4Writer. Eliminates the native
                            // "MPEG4Writer: Stop() called but track is not started or
                            // stopped" E-log on cancel/timeout/error paths and on
                            // sources whose audio track carries zero samples, and is
                            // more tolerant of edge-case tracks than the native writer.
                            .setMuxerFactory(new InAppMp4Muxer.Factory())
                            .setEncoderFactory(new DefaultEncoderFactory.Builder(context)
                                    .setRequestedVideoEncoderSettings(
                                            new VideoEncoderSettings.Builder()
                                                    .setBitrate(TARGET_VIDEO_BITRATE)
                                                    .build())
                                    .build())
                            .addListener(new Transformer.Listener() {
                                @Override
                                public void onCompleted(@NonNull Composition composition,
                                                        @NonNull ExportResult exportResult) {
                                    latch.countDown();
                                }

                                @Override
                                public void onError(@NonNull Composition composition,
                                                    @NonNull ExportResult exportResult,
                                                    @NonNull ExportException exportException) {
                                    error.set(exportException);
                                    latch.countDown();
                                }
                            })
                            .build();
                    transformerRef.set(transformer);

                    EditedMediaItem edited =
                            new EditedMediaItem.Builder(MediaItem.fromUri(inputUri))
                                    .setEffects(new Effects(
                                            Collections.emptyList(),
                                            Collections.singletonList(
                                                    Presentation.createForHeight(outputHeight))))
                                    .build();
                    transformer.start(edited, outputFile.getAbsolutePath());
                } catch (RuntimeException re) {
                    error.set(re);
                    latch.countDown();
                }
            });

            long timeoutMs = transcodeTimeoutMs(originalSizeBytes);
            boolean finished;
            try {
                finished = latch.await(timeoutMs, TimeUnit.MILLISECONDS);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                Log.w(TAG, "Slot " + slotIndex + ": interrupted — cancelling transcode");
                cancelAndCleanUp(handler, transformerRef, outputFile);
                return null;
            }
            if (!finished) {
                Log.w(TAG, "Slot " + slotIndex + ": transcode timed out after "
                        + timeoutMs + " ms — cancelling");
                cancelAndCleanUp(handler, transformerRef, outputFile);
                return null;
            }

            Exception err = error.get();
            if (err != null) {
                Log.w(TAG, "Slot " + slotIndex + ": transcode failed for " + inputUri
                        + " (" + err.getMessage() + ") — raw fallback");
                deleteQuietly(outputFile);
                return null;
            }

            // ── Savings check: keep the result only if it is actually smaller. ──
            long transcodedSize = outputFile.length();
            if (transcodedSize <= 0 || transcodedSize >= originalSizeBytes) {
                Log.d(TAG, "Slot " + slotIndex + ": no savings (" + originalSizeBytes
                        + " B → " + transcodedSize + " B) — raw fallback");
                deleteQuietly(outputFile);
                return null;
            }
            Log.d(TAG, "Slot " + slotIndex + ": transcoded " + originalSizeBytes
                    + " B → " + transcodedSize + " B");
            return outputFile;
        } catch (RuntimeException e) {
            Log.w(TAG, "Slot " + slotIndex + ": transcode error (" + e + ") — raw fallback");
            deleteQuietly(outputFile);
            return null;
        } finally {
            // Pending posts (including cancelAndCleanUp's) still run before quit.
            handlerThread.quitSafely();
        }
    }

    /**
     * Posts {@link Transformer#cancel()} followed by temp-file deletion onto the
     * transformer's own Looper. Ordering matters: cancel must release the muxer's
     * file handle before the file is deleted.
     */
    private static void cancelAndCleanUp(@NonNull Handler handler,
                                         @NonNull AtomicReference<Transformer> transformerRef,
                                         @NonNull File outputFile) {
        handler.post(() -> {
            Transformer transformer = transformerRef.get();
            if (transformer != null) {
                try {
                    transformer.cancel();
                } catch (RuntimeException e) {
                    Log.w(TAG, "cancel() failed: " + e.getMessage());
                }
            }
            deleteQuietly(outputFile);
        });
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * Reads source dimensions / rotation / bitrate via {@link MediaMetadataRetriever}.
     * Returns {@code null} when the source has no readable video track — i.e. it is
     * audio-only, corrupt, or not a media file at all despite its extension. Callers
     * treat {@code null} as "do not transcode" and fall back to the raw stream.
     */
    @Nullable
    private static VideoInfo probe(@NonNull Context context, @NonNull Uri uri) {
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(context, uri);
            if (!"yes".equals(retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO))) {
                return null; // audio-only or not a media file at all
            }
            int width = parsePositiveInt(retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH));
            int height = parsePositiveInt(retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT));
            int rotation = parsePositiveInt(retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION));
            int bitrate = parsePositiveInt(retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_BITRATE));
            if (width <= 0 || height <= 0) {
                return null;
            }
            // After rotation, the display height of a 90°/270° video is its stored width.
            int effectiveHeight = (rotation == 90 || rotation == 270) ? width : height;
            return new VideoInfo(Math.min(width, height), effectiveHeight, bitrate);
        } catch (Exception e) {
            return null;
        } finally {
            try {
                retriever.release();
            } catch (Exception ignored) {
                // release() declares IOException on newer SDKs — nothing to do.
            }
        }
    }

    private static int parsePositiveInt(@Nullable String value) {
        if (value == null) return -1;
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException nfe) {
            return -1;
        }
    }

    /**
     * Size-proportional export timeout: 60s base + 1s per source MB, capped at 15 min.
     */
    private static long transcodeTimeoutMs(long sizeBytes) {
        long mb = Math.max(1, sizeBytes / (1024L * 1024L));
        return Math.min(BASE_TIMEOUT_MS + mb * PER_MB_TIMEOUT_MS, MAX_TIMEOUT_MS);
    }

    private static void deleteQuietly(@Nullable File file) {
        if (file != null && file.exists() && !file.delete()) {
            Log.w(TAG, "Failed to delete temp file: " + file.getName());
        }
    }

    /**
     * Rotation-aware source video metadata (immutable value holder).
     *
     * @param shortSide       min(width, height) — rotation-agnostic "p" class of the video.
     * @param effectiveHeight Display height after applying the rotation flag.
     * @param bitrate         Total container bitrate in bps, or -1 if unknown.
     */
    private record VideoInfo(int shortSide, int effectiveHeight, int bitrate) {
    }
}
