# Subsonic API Compatibility | Navidrome
Are you a Subsonic client developer? Check out the API features supported by Navidrome

### Supported Subsonic API endpoints[](#supported-subsonic-api-endpoints)

Navidrome is currently compatible with [Subsonic API](http://www.subsonic.org/pages/api.jsp) v1.16.1, with some exceptions.

[OpenSubsonic](https://opensubsonic.netlify.app/) extensions are being constantly added. For an up to date list of supported extensions, check [here](https://github.com/navidrome/navidrome/issues/2695).

This is a (hopefully) up-to-date list of all Subsonic API endpoints implemented in Navidrome. Check the “Notes” column for limitations/missing behavior. Also keep in mind these differences between Navidrome and Subsonic:

*   Navidrome will not implement any video related functionality, it is focused on Music only
*   Navidrome supports [multiple Music Libraries (Music Folders)](https://www.navidrome.org/docs/usage/features/multi-library/) with user-specific access controls
*   There are currently no plans to support browse-by-folder. Endpoints for this functionality (Ex: `getIndexes`, `getMusicDirectory`) returns a simulated directory tree, using the format: `/Artist/Album/01 - Song.mp3`.
*   Navidrome does not mark songs as played by calls to `stream`, only when `scrobble` is called with `submission=true`
*   IDs in Navidrome are always strings, normally MD5 hashes or UUIDs. This is important to mention because, even though the Subsonic API [schema](http://www.subsonic.org/pages/inc/api/schema/subsonic-rest-api-1.16.1.xsd) specifies IDs as strings, some clients insist in converting IDs to integers


|System    |               |
|----------|---------------|
|ping      |               |
|getLicense|Always valid ;)|



|Browsing         |                                                          |
|-----------------|----------------------------------------------------------|
|getMusicFolders  |Returns all libraries accessible to the authenticated user|
|getIndexes       |Doesn’t support shortcuts, nor direct children            |
|getMusicDirectory|                                                          |
|getSong          |                                                          |
|getArtists       |                                                          |
|getArtist        |                                                          |
|getAlbum         |                                                          |
|getGenres        |                                                          |
|getArtistInfo    |Requires external integrations                            |
|getArtistInfo2   |Requires external integrations                            |
|getAlbumInfo     |Requires external integrations                            |
|getAlbumInfo2    |Requires external integrations                            |
|getTopSongs      |Requires Last.fm integration                              |
|getSimilarSongs  |Requires Last.fm integration                              |
|getSimilarSongs2 |Requires Last.fm integration                              |



|Album/Songs Lists|   |
|-----------------|---|
|getAlbumList     |   |
|getAlbumList2    |   |
|getStarred       |   |
|getStarred2      |   |
|getNowPlaying    |   |
|getRandomSongs   |   |
|getSongsByGenre  |   |



|Searching|                                                                 |
|---------|-----------------------------------------------------------------|
|search2  |Doesn’t support Lucene queries, only simple auto complete queries|
|search3  |Doesn’t support Lucene queries, only simple auto complete queries|



|Playlists     |                                     |
|--------------|-------------------------------------|
|getPlaylists  |username parameter is not implemented|
|getPlaylist   |                                     |
|createPlaylist|                                     |
|updatePlaylist|                                     |
|deletePlaylist|                                     |




* Media Retrieval: stream
* Media Retrieval: download
  * Accepts ids for Songs, Albums, Artists and Playlists. Also accepts transcoding options similar to stream
* Media Retrieval: getCoverArt
* Media Retrieval: getLyrics
  * Works with embedded lyrics and external files
* Media Retrieval: getAvatar
  * If Gravatar is enabled and the user has an email, returns a redirect to their Gravatar. Or else returns a placeholder



|Media Annotation|   |
|----------------|---|
|star            |   |
|unstar          |   |
|setRating       |   |
|scrobble        |   |




* Bookmarks: getBookmarks
* Bookmarks: createBookmark
* Bookmarks: deleteBookmark
* Bookmarks: getPlayQueue
  * current is a string id, not int as it shows in the official Subsonic API documentation
* Bookmarks: savePlayQueue



|Sharing (if EnableSharing is true)|   |
|----------------------------------|---|
|getShares                         |   |
|createShare                       |   |
|updateShare                       |   |
|deleteShare                       |   |



|Internet radio            |   |
|--------------------------|---|
|getInternetRadioStations  |   |
|createInternetRadioStation|   |
|updateInternetRadioStation|   |
|deleteInternetRadioStation|   |




* User Management: getUser
  * Ignores username parameter, and returns the user identified in the authentication. Roles reflect actual server capabilities and user permissions. For example: downloadRole depends on download being enabled, jukeboxRole depends on jukebox being enabled, etc. Note that some features like ratings and favorites are always available to all users regardless of roles
* User Management: getUsers
  * Returns only the user identified in the authentication



|Media library scanning|                                                             |
|----------------------|-------------------------------------------------------------|
|getScanStatus         |Also returns the extra fields lastScan and folderCount       |
|startScan             |Accepts an extra fullScan boolean param, to force a full scan|
