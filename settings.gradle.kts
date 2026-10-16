pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // GeckoView (Firefox's engine) for the in-app browser: only Mozilla's own packages come from here.
        maven {
            url = uri("https://maven.mozilla.org/maven2/")
            content { includeGroupByRegex("org\\.mozilla\\..*") }
        }
    }
}
rootProject.name = "NewAlCloud"
include(":app")
project(":app").projectDir = file("android-lite/app")
