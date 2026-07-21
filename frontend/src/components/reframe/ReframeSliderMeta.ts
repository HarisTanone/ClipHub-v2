/**
 * Metadata mapping for all 21 Reframe Tuning slider parameters.
 *
 * Provides descriptions and tooltips for each parameter to give users
 * contextual guidance when adjusting values in the Settings UI.
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SliderMeta {
  description: string;
  tooltip: {
    what: string;
    increase: string;
    decrease: string;
  };
}

/** All 21 keys from the ReframeTuning interface */
export type ReframeTuningKey =
  | "sample_interval_sec"
  | "max_samples"
  | "face_confidence"
  | "min_face_size_ratio"
  | "max_face_size_ratio"
  | "min_separation_ratio"
  | "min_coexist_ratio"
  | "dominance_single_crop"
  | "grid_base_zoom"
  | "grid_max_zoom"
  | "grid_face_margin"
  | "grid_enter_samples"
  | "grid_exit_samples"
  | "min_grid_segment_seconds"
  | "min_face_area_px"
  | "min_area_ratio_to_max"
  | "min_frame_ratio"
  | "ghost_iou_threshold"
  | "ghost_center_dist_ratio"
  | "ghost_center_dist_broad"
  | "min_pair_size_ratio";

// ─── Slider Metadata ─────────────────────────────────────────────────────────

export const REFRAME_SLIDER_META: Record<ReframeTuningKey, SliderMeta> = {
  // ── Sampling & Detection ─────────────────────────────────────────────────

  sample_interval_sec: {
    description: "Interval sampling frame untuk deteksi wajah (~3fps default)",
    tooltip: {
      what: "Jarak waktu antar frame yang dianalisis untuk mendeteksi wajah",
      increase: "Lebih sedikit frame dianalisis, proses lebih cepat tapi kurang akurat",
      decrease: "Lebih banyak frame dianalisis, deteksi lebih halus tapi proses lebih lama",
    },
  },

  max_samples: {
    description: "Jumlah maksimum frame yang dianalisis per klip",
    tooltip: {
      what: "Batas atas jumlah frame yang akan di-scan untuk deteksi wajah",
      increase: "Coverage lebih baik untuk klip panjang, tapi proses lebih lama",
      decrease: "Proses lebih cepat, tapi bisa melewatkan momen penting di klip panjang",
    },
  },

  face_confidence: {
    description: "Threshold kepercayaan deteksi wajah MediaPipe",
    tooltip: {
      what: "Skor minimum agar deteksi dianggap sebagai wajah valid",
      increase: "Lebih sedikit false positive, tapi wajah terhalang bisa terlewat",
      decrease: "Lebih banyak wajah terdeteksi, tapi noise dan false positive meningkat",
    },
  },

  min_face_size_ratio: {
    description: "Ukuran minimum wajah relatif terhadap lebar frame",
    tooltip: {
      what: "Filter wajah yang terlalu kecil (jauh dari kamera)",
      increase: "Hanya wajah besar/dekat yang diterima, wajah jauh diabaikan",
      decrease: "Wajah kecil/jauh juga ikut terdeteksi",
    },
  },

  max_face_size_ratio: {
    description: "Ukuran maksimum wajah relatif terhadap lebar frame",
    tooltip: {
      what: "Filter wajah yang terlalu besar (extreme close-up)",
      increase: "Toleransi lebih tinggi untuk wajah besar di frame",
      decrease: "Close-up ekstrem akan difilter lebih agresif",
    },
  },

  min_separation_ratio: {
    description: "Jarak horizontal minimum antar 2 wajah untuk dianggap terpisah",
    tooltip: {
      what: "Threshold jarak horizontal untuk mengaktifkan mode grid/split-screen",
      increase: "Kedua orang harus lebih berjauhan untuk trigger grid mode",
      decrease: "Grid mode aktif meski dua orang berdekatan",
    },
  },

  min_coexist_ratio: {
    description: "Persentase frame di mana kedua wajah harus muncul bersamaan",
    tooltip: {
      what: "Syarat berapa banyak frame yang harus memiliki 2 wajah sekaligus untuk aktifkan grid",
      increase: "Kedua orang harus hadir di lebih banyak frame untuk trigger grid",
      decrease: "Grid mode lebih mudah aktif meski salah satu sering hilang",
    },
  },

  // ── Auto Grid / Split-Screen ─────────────────────────────────────────────

  dominance_single_crop: {
    description: "Threshold dominasi satu orang untuk skip grid mode",
    tooltip: {
      what: "Jika satu orang muncul di lebih dari X% frame, gunakan single crop saja",
      increase: "Lebih sulit skip grid — perlu dominasi sangat tinggi",
      decrease: "Lebih mudah fallback ke single crop meski ada 2 orang",
    },
  },

  grid_base_zoom: {
    description: "Zoom default setiap panel grid",
    tooltip: {
      what: "Level zoom dasar yang diterapkan pada setiap panel split-screen",
      increase: "Crop lebih ketat pada wajah, background lebih sedikit terlihat",
      decrease: "Lebih banyak background terlihat di setiap panel",
    },
  },

  grid_max_zoom: {
    description: "Zoom maksimum saat 2 wajah berdekatan",
    tooltip: {
      what: "Batas zoom tertinggi untuk memisahkan wajah yang berdekatan di grid",
      increase: "Crop lebih agresif saat wajah berdekatan, separasi lebih jelas",
      decrease: "Zoom lebih konservatif, wajah berdekatan bisa tetap overlap",
    },
  },

  grid_face_margin: {
    description: "Ruang napas minimum di sekitar wajah dalam panel grid",
    tooltip: {
      what: "Padding di sekitar wajah agar tidak terpotong terlalu ketat",
      increase: "Lebih banyak ruang di sekitar wajah, tampilan lebih longgar",
      decrease: "Crop lebih ketat ke wajah, risiko terpotong meningkat",
    },
  },

  grid_enter_samples: {
    description: "Frame berturutan untuk konfirmasi orang ke-2 sebelum grid aktif",
    tooltip: {
      what: "Anti-flicker: berapa frame berturutan harus ada 2 wajah sebelum grid menyala",
      increase: "Grid lebih lambat aktif, tapi lebih stabil (anti-flicker kuat)",
      decrease: "Grid lebih cepat aktif, tapi bisa berkedip jika deteksi tidak stabil",
    },
  },

  grid_exit_samples: {
    description: "Frame berturutan sebelum grid dinonaktifkan",
    tooltip: {
      what: "Berapa frame berturutan tanpa 2 wajah sebelum grid ditutup",
      increase: "Grid bertahan lebih lama meski satu orang sempat hilang",
      decrease: "Grid lebih cepat ditutup saat satu orang pergi",
    },
  },

  min_grid_segment_seconds: {
    description: "Durasi minimum segment grid (anti rapid-switching)",
    tooltip: {
      what: "Berapa detik minimum sebuah segment grid harus bertahan",
      increase: "Segment grid lebih panjang, menghindari switch cepat",
      decrease: "Grid bisa muncul dan hilang lebih cepat (risiko flicker)",
    },
  },

  // ── Ghost Detection / False Positive Filtering ───────────────────────────

  min_face_area_px: {
    description: "Area pixel minimum untuk wajah valid",
    tooltip: {
      what: "Filter deteksi wajah yang terlalu kecil (dalam pixel)",
      increase: "Hanya wajah besar yang diterima, deteksi kecil dianggap ghost",
      decrease: "Wajah kecil/jauh juga dianggap valid (studio radio, dll.)",
    },
  },

  min_area_ratio_to_max: {
    description: "Rasio ukuran minimum terhadap wajah terbesar yang terdeteksi",
    tooltip: {
      what: "Wajah harus minimal X% ukuran wajah terbesar untuk dianggap valid",
      increase: "Filter lebih agresif — hanya wajah berukuran mirip yang diterima",
      decrease: "Toleransi perbedaan ukuran lebih besar (orang jauh tetap valid)",
    },
  },

  min_frame_ratio: {
    description: "Persentase minimum kemunculan wajah di frame yang disampling",
    tooltip: {
      what: "Track wajah harus muncul di minimal X% frame untuk dianggap nyata",
      increase: "Hanya wajah yang konsisten hadir yang diterima",
      decrease: "Wajah yang muncul sebentar juga dianggap valid",
    },
  },

  ghost_iou_threshold: {
    description: "Threshold overlap bounding box untuk deteksi duplikat",
    tooltip: {
      what: "IoU (Intersection over Union) untuk mendeteksi track wajah yang sama",
      increase: "Perlu overlap lebih besar untuk dianggap duplikat (lebih permisif)",
      decrease: "Overlap kecil sudah dianggap duplikat (filter lebih agresif)",
    },
  },

  ghost_center_dist_ratio: {
    description: "Jarak pusat wajah untuk pengecekan ghost proximity",
    tooltip: {
      what: "Jarak normalized antara pusat dua wajah untuk cek ghost",
      increase: "Wajah harus lebih berjauhan untuk dianggap berbeda",
      decrease: "Wajah berdekatan lebih mudah dianggap orang berbeda",
    },
  },

  ghost_center_dist_broad: {
    description: "Jarak pusat broad dikombinasikan dengan kemiripan area",
    tooltip: {
      what: "Pengecekan ghost lebih luas: jarak pusat + kemiripan ukuran",
      increase: "Radius cek ghost lebih besar, lebih banyak yang terfilter",
      decrease: "Pengecekan ghost lebih ketat, hanya yang sangat dekat terfilter",
    },
  },

  min_pair_size_ratio: {
    description: "Rasio ukuran minimum antara wajah besar dan kecil untuk pair valid",
    tooltip: {
      what: "Perbandingan ukuran minimum antara dua wajah untuk membentuk pasangan valid",
      increase: "Kedua wajah harus berukuran lebih mirip untuk dipasangkan",
      decrease: "Wajah besar dan kecil lebih mudah dipasangkan (perbedaan jarak toleransi)",
    },
  },
};

// ─── Section Descriptions ────────────────────────────────────────────────────

export interface SectionMeta {
  title: string;
  pipelineStage: string;
  description: string;
}

export const REFRAME_SECTION_DESCRIPTIONS: Record<string, SectionMeta> = {
  samplingDetection: {
    title: "Sampling & Detection",
    pipelineStage: "Frame Sampling",
    description:
      "Mengontrol seberapa sering dan seberapa sensitif engine menganalisis frame video untuk mendeteksi wajah. Mempengaruhi akurasi deteksi dan kecepatan proses.",
  },
  autoGrid: {
    title: "Auto Grid / Split-Screen (Detect-Then-Switch)",
    pipelineStage: "Split-Screen Composition",
    description:
      "Split-screen composition v2 memakai detect-then-switch: 1 orang = no-grid single. ≥2 orang berbeda dalam 1 frame yang sama → auto-switch ke 2-grid 50:50. Grid hanya aktif jika toggle frontend aktif (9:16 only). Orang per panel tidak boleh sama (distinct identity + ghost check). Jika kejauhan zoom, gunakan transisi pilihan user untuk single→grid (cut/fade/slide/zoom). Mulai single di t=0, bukan langsung grid. Headroom fix: kepala tidak kepotong.",
  },
  ghostDetection: {
    title: "Ghost Detection",
    pipelineStage: "False-Positive Filtering",
    description:
      "Memfilter deteksi wajah palsu (ghost): noise, duplikat track, dan wajah terlalu kecil. Memastikan hanya wajah nyata yang masuk ke proses reframe.",
  },
};
