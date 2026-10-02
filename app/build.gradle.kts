plugins {
    id("com.android.application")
}

android {
    namespace = "com.musab.newalcloud"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.musab.newalcloud"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

// No third-party dependencies: the platform's HttpURLConnection and org.json are enough.
