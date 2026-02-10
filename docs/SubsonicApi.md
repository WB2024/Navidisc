# Subsonic
The Subsonic API allows anyone to build their own programs using Subsonic as the media server, whether they're on the web, the desktop or on mobile devices. All the Subsonic [apps](apps.jsp) are built using the Subsonic API.

Feel free to join the [Subsonic App Developers](http://groups.google.com/group/subsonic-app-developers) group for discussions, suggestions and questions.

### Introduction

The Subsonic API allows you to call methods that respond in [REST](http://en.wikipedia.org/wiki/Representational_State_Transfer) style xml. Individual methods are detailed below.

Please note that all methods take the following parameters:



* Parameter: u
  * Required: Yes
  * Default: 
  * Comment: The username.
* Parameter: p
  * Required: Yes*
  * Default: 
  * Comment: The password, either in clear text or hex-encoded with a "enc:" prefix. Since 1.13.0                this should only be used for testing purposes.
* Parameter: t
  * Required: Yes*
  * Default: 
  * Comment: (Since 1.13.0) The authentication token computed as md5(password + salt).                See below for details.
* Parameter: s
  * Required: Yes*
  * Default: 
  * Comment: (Since 1.13.0) A random string ("salt") used as input for computing the password hash.                See below for details.
* Parameter: v
  * Required: Yes
  * Default: 
  * Comment: The protocol version implemented by the client, i.e., the version of the                subsonic-rest-api.xsd schema used (see below).            
* Parameter: c
  * Required: Yes
  * Default: 
  * Comment: A unique string identifying the client application.
* Parameter: f
  * Required: No
  * Default: xml
  * Comment: Request data to be returned in this format. Supported values are "xml", "json" (since 1.4.0) and "jsonp" (since 1.6.0). If                using jsonp, specify name of javascript callback function using a callback                parameter.            


\*) Either `p` or _both_ `t` and `s` must be specified.

Remember to [URL encode](http://www.w3schools.com/tags/ref_urlencode.asp) the request parameters. All methods (except those that return binary data) returns XML documents conforming to the [subsonic-rest-api.xsd](#versions) schema. The XML documents are encoded with UTF-8.

### Authentication

If your targeting API version [1.12.0](#versions) or earlier, authentication is performed by sending the password as clear text or hex-encoded. Examples:

`http://your-server/rest/ping.view?u=joe&p=sesame&v=1.12.0&c=myapp`  
`http://your-server/rest/ping.view?u=joe&p=enc:736573616d65&v=1.12.0&c=myapp`

Starting with API version [1.13.0](#versions), the recommended authentication scheme is to send an authentication token, calculated as a _one-way salted hash_ of the password.

This involves two steps:

1.  For each REST call, generate a random string called the _salt_. Send this as parameter `s`.
Use a salt length of at least six characters.2.  Calculate the authentication token as follows: **token = md5(password + salt)**. The md5() function takes a string and returns the 32-byte ASCII hexadecimal representation of the MD5 hash, using lower case characters for the hex values. The '+' operator represents concatenation of the two strings. Treat the strings as UTF-8 encoded when calculating the hash. Send the result as parameter `t`.

For example: if the password is **sesame** and the random salt is **c19b2d**, then **token = md5("sesamec19b2d") = 26719a1196d2a940705a59634eb18eab**. The corresponding request URL then becomes:

`http://your-server/rest/ping.view?u=joe&t=26719a1196d2a940705a59634eb18eab&s=c19b2d&v=1.12.0&c=myapp`

### Error handling

If a method fails it will return an error code and message in an `<error>` element. In addition, the `status` attribute of the `<subsonic-response>` root element will be set to `failed` instead of `ok`. For example:

<?xml version="1.0" encoding="UTF-8"?>  
<subsonic-response xmlns="http://subsonic.org/restapi" status="failed" version="1.1.0">  
   <error code="40" message="Wrong username or password"/>  
</subsonic-response>  

The following error codes are defined:



* Code: 0
  * Description: A generic error.
* Code: 10
  * Description: Required parameter is missing.
* Code: 20
  * Description: Incompatible Subsonic REST protocol version. Client must upgrade.
* Code: 30
  * Description: Incompatible Subsonic REST protocol version. Server must upgrade.
* Code: 40
  * Description: Wrong username or password.
* Code: 41
  * Description: Token authentication not supported for LDAP users.
* Code: 50
  * Description: User is not authorized for the given operation.
* Code: 60
  * Description: The trial period for the Subsonic server is over. Please upgrade to Subsonic Premium.                Visit subsonic.org for details.            
* Code: 70
  * Description: The requested data was not found.


### Versions

This table shows the REST API version implemented in different Subsonic versions:

Note that a Subsonic server is backward compatible with a REST client if and only if the major version is the same, and the minor version of the client is less than or equal to the server's. For example, if the server has REST API version 2.2, it supports client versions 2.0, 2.1 and 2.2, but not versions 1.x, 2.3+ or 3.x. The third part of the version number is not used to determine compatibility.

### File structure vs ID3 tags

Starting with version [1.8.0](#versions), the API provides methods for accessing the media collection organized according to ID3 tags, rather than file structure.

For instance, browsing through the collection using ID3 tags should use the `getArtists`, `getArtist` and `getAlbum` methods. To browse using file structure you would use `getIndexes` and `getMusicDirectory`.

Correspondingly, there are two sets of methods for searching, starring and album lists. Refer to the method documentation for details.

API method documentation
------------------------

### ping

`http://your-server/rest/ping` Since [1.0.0](#versions)

Used to test connectivity with the server. Takes no extra parameters.

Returns an empty `<subsonic-response>` element on success. [Example](inc/api/examples/ping_example_1.xml).

### getLicense

`http://your-server/rest/getLicense` Since [1.0.0](#versions)

Get details about the software license. Takes no extra parameters. Please note that access to the REST API requires that the server has a valid license (after a 30-day trial period). To get a license key you must upgrade to [Subsonic Premium](premium.jsp).

Returns a `<subsonic-response>` element with a nested `<license>` element on success. [Example](inc/api/examples/license_example_1.xml).

### getMusicFolders

`http://your-server/rest/getMusicFolders` Since [1.0.0](#versions)

Returns all configured top-level music folders. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<musicFolders>` element on success. [Example](inc/api/examples/musicFolders_example_1.xml).

### getIndexes

`http://your-server/rest/getIndexes` Since [1.0.0](#versions)

Returns an indexed structure of all artists.



* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: If specified, only return artists in the music folder with the given ID. See                getMusicFolders.            
* Parameter: ifModifiedSince
  * Required: No
  * Default: 
  * Comment: If specified, only return a result if the artist collection has changed since the given time (in                milliseconds since 1 Jan 1970).            


Returns a `<subsonic-response>` element with a nested `<indexes>` element on success. [Example](inc/api/examples/indexes_example_1.xml).

### getMusicDirectory

`http://your-server/rest/getMusicDirectory`  
Since [1.0.0](#versions)

Returns a listing of all files in a music directory. Typically used to get list of albums for an artist, or list of songs for an album.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the music folder. Obtained by calls to getIndexes or                getMusicDirectory.            


Returns a `<subsonic-response>` element with a nested `<directory>` element on success. [Example 1](inc/api/examples/directory_example_1.xml). [Example 2](inc/api/examples/directory_example_2.xml).

### getGenres

`http://your-server/rest/getGenres` Since [1.9.0](#versions)

Returns all genres.

Returns a `<subsonic-response>` element with a nested `<genres>` element on success. [Example](inc/api/examples/genres_example_1.xml).

### getArtists

`http://your-server/rest/getArtists` Since [1.8.0](#versions)

Similar to `getIndexes`, but organizes music according to ID3 tags.



* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: If specified, only return artists in the music folder with the given ID. See                getMusicFolders.            


Returns a `<subsonic-response>` element with a nested `<artists>` element on success. [Example](inc/api/examples/artists_example_1.xml).

### getArtist

`http://your-server/rest/getArtist` Since [1.8.0](#versions)

Returns details for an artist, including a list of albums. This method organizes music according to ID3 tags.


|Parameter|Required|Default|Comment       |
|---------|--------|-------|--------------|
|id       |Yes     |       |The artist ID.|


Returns a `<subsonic-response>` element with a nested `<artist>` element on success. [Example](inc/api/examples/artist_example_1.xml).

### getAlbum

`http://your-server/rest/getAlbum`  
Since [1.8.0](#versions)

Returns details for an album, including a list of songs. This method organizes music according to ID3 tags.


|Parameter|Required|Default|Comment      |
|---------|--------|-------|-------------|
|id       |Yes     |       |The album ID.|


Returns a `<subsonic-response>` element with a nested `<album>` element on success. [Example](inc/api/examples/album_example_1.xml).

### getSong

`http://your-server/rest/getSong` Since [1.8.0](#versions)

Returns details for a song.


|Parameter|Required|Default|Comment     |
|---------|--------|-------|------------|
|id       |Yes     |       |The song ID.|


Returns a `<subsonic-response>` element with a nested `<song>` element on success. [Example](inc/api/examples/song_example_1.xml).

### getVideos

`http://your-server/rest/getVideos` Since [1.8.0](#versions)

Returns all video files.

Returns a `<subsonic-response>` element with a nested `<videos>` element on success. [Example](inc/api/examples/videos_example_1.xml).

### getVideoInfo

`http://your-server/rest/getVideoInfo` Since [1.14.0](#versions)

Returns details for a video, including information about available audio tracks, subtitles (captions) and conversions.


|Parameter|Required|Default|Comment      |
|---------|--------|-------|-------------|
|id       |Yes     |       |The video ID.|


Returns a `<subsonic-response>` element with a nested `<videoInfo>` element on success. [Example](inc/api/examples/videoInfo_example_1.xml).

### getArtistInfo

`http://your-server/rest/getArtistInfo` Since [1.11.0](#versions)

Returns artist info with biography, image URLs and similar artists, using data from [last.fm](http://last.fm/).



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: The artist, album or song ID.
* Parameter: count
  * Required: No
  * Default: 20
  * Comment: Max number of similar artists to return.
* Parameter: includeNotPresent
  * Required: No
  * Default: false
  * Comment: Whether to return artists that are not present in the media library.


Returns a `<subsonic-response>` element with a nested `<artistInfo>` element on success. [Example](inc/api/examples/artistInfo_example_1.xml).

### getArtistInfo2

`http://your-server/rest/getArtistInfo2` Since [1.11.0](#versions)

Similar to `getArtistInfo`, but organizes music according to ID3 tags.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: The artist ID.
* Parameter: count
  * Required: No
  * Default: 20
  * Comment: Max number of similar artists to return.
* Parameter: includeNotPresent
  * Required: No
  * Default: false
  * Comment: Whether to return artists that are not present in the media library.


Returns a `<subsonic-response>` element with a nested `<artistInfo2>` element on success. [Example](inc/api/examples/artistInfo2_example_1.xml).

### getAlbumInfo

`http://your-server/rest/getAlbumInfo` Since [1.14.0](#versions)

Returns album notes, image URLs etc, using data from [last.fm](http://last.fm/).


|Parameter|Required|Default|Comment              |
|---------|--------|-------|---------------------|
|id       |Yes     |       |The album or song ID.|


Returns a `<subsonic-response>` element with a nested `<albumInfo>` element on success. [Example](inc/api/examples/albumInfo_example_1.xml).

### getAlbumInfo2

`http://your-server/rest/getAlbumInfo2` Since [1.14.0](#versions)

Similar to `getAlbumInfo`, but organizes music according to ID3 tags.


|Parameter|Required|Default|Comment      |
|---------|--------|-------|-------------|
|id       |Yes     |       |The album ID.|


Returns a `<subsonic-response>` element with a nested `<albumInfo>` element on success. [Example](inc/api/examples/albumInfo_example_1.xml).

### getSimilarSongs

`http://your-server/rest/getSimilarSongs` Since [1.11.0](#versions)

Returns a random collection of songs from the given artist and similar artists, using data from [last.fm](http://last.fm/). Typically used for artist radio features.


|Parameter|Required|Default|Comment                       |
|---------|--------|-------|------------------------------|
|id       |Yes     |       |The artist, album or song ID. |
|count    |No      |50     |Max number of songs to return.|


Returns a `<subsonic-response>` element with a nested `<similarSongs>` element on success. [Example](inc/api/examples/similarSongs_example_1.xml).

### getSimilarSongs2

`http://your-server/rest/getSimilarSongs2` Since [1.11.0](#versions)

Similar to `getSimilarSongs`, but organizes music according to ID3 tags.


|Parameter|Required|Default|Comment                       |
|---------|--------|-------|------------------------------|
|id       |Yes     |       |The artist ID.                |
|count    |No      |50     |Max number of songs to return.|


Returns a `<subsonic-response>` element with a nested `<similarSongs2>` element on success. [Example](inc/api/examples/similarSongs2_example_1.xml).

### getTopSongs

`http://your-server/rest/getTopSongs` Since [1.13.0](#versions)

Returns top songs for the given artist, using data from [last.fm](http://last.fm/).


|Parameter|Required|Default|Comment                       |
|---------|--------|-------|------------------------------|
|artist   |Yes     |       |The artist name.              |
|count    |No      |50     |Max number of songs to return.|


Returns a `<subsonic-response>` element with a nested `<topSongs>` element on success. [Example](inc/api/examples/topSongs_example_1.xml).

### getAlbumList

`http://your-server/rest/getAlbumList` Since [1.2.0](#versions)

Returns a list of random, newest, highest rated etc. albums. Similar to the album lists on the home page of the Subsonic web interface.



* Parameter: type
  * Required: Yes
  * Default: 
  * Comment: The list type. Must be one of the following: random, newest,                highest, frequent, recent. Since 1.8.0                you can also use alphabeticalByName or alphabeticalByArtist to page through                all albums alphabetically, and starred to retrieve starred albums.                Since 1.10.1 you can use byYear and byGenre to list                albums in a given year range or genre.            
* Parameter: size
  * Required: No
  * Default: 10
  * Comment: The number of albums to return. Max 500.
* Parameter: offset
  * Required: No
  * Default: 0
  * Comment: The list offset. Useful if you for example want to page through the list of newest albums.
* Parameter: fromYear
  * Required: Yes (if type is byYear)
  * Default: 
  * Comment: The first year in the range. If fromYear > toYear a reverse chronological list is returned.
* Parameter: toYear
  * Required: Yes (if type is byYear)
  * Default: 
  * Comment: The last year in the range.
* Parameter: genre
  * Required: Yes (if type is byGenre)
  * Default: 
  * Comment: The name of the genre, e.g., "Rock".
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.11.0) Only return albums in the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<albumList>` element on success. [Example](inc/api/examples/albumList_example_1.xml).

### getAlbumList2

`http://your-server/rest/getAlbumList2` Since [1.8.0](#versions)

Similar to `getAlbumList`, but organizes music according to ID3 tags.



* Parameter: type
  * Required: Yes
  * Default: 
  * Comment: The list type. Must be one of the following: random, newest,                frequent, recent, starred,                alphabeticalByName or alphabeticalByArtist.                Since 1.10.1 you can use byYear and byGenre to list                albums in                a given year range or genre.            
* Parameter: size
  * Required: No
  * Default: 10
  * Comment: The number of albums to return. Max 500.
* Parameter: offset
  * Required: No
  * Default: 0
  * Comment: The list offset. Useful if you for example want to page through the list of newest albums.
* Parameter: fromYear
  * Required: Yes (if type is byYear)
  * Default: 
  * Comment: The first year in the range. If fromYear > toYear a reverse chronological list is returned.
* Parameter: toYear
  * Required: Yes (if type is byYear)
  * Default: 
  * Comment: The last year in the range.
* Parameter: genre
  * Required: Yes (if type is byGenre)
  * Default: 
  * Comment: The name of the genre, e.g., "Rock".
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return albums in the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<albumList2>` element on success. [Example](inc/api/examples/albumList2_example_1.xml).

### getRandomSongs

`http://your-server/rest/getRandomSongs` Since [1.2.0](#versions)

Returns random songs matching the given criteria.



* Parameter: size
  * Required: No
  * Default: 10
  * Comment: The maximum number of songs to return. Max 500.
* Parameter: genre
  * Required: No
  * Default: 
  * Comment: Only returns songs belonging to this genre.
* Parameter: fromYear
  * Required: No
  * Default: 
  * Comment: Only return songs published after or in this year.
* Parameter: toYear
  * Required: No
  * Default: 
  * Comment: Only return songs published before or in this year.
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: Only return songs in the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<randomSongs>` element on success. [Example](inc/api/examples/randomSongs_example_1.xml).

### getSongsByGenre

`http://your-server/rest/getSongsByGenre` Since [1.9.0](#versions)

Returns songs in a given genre.



* Parameter: genre
  * Required: Yes
  * Default: 
  * Comment: The genre, as returned by getGenres.
* Parameter: count
  * Required: No
  * Default: 10
  * Comment: The maximum number of songs to return. Max 500.
* Parameter: offset
  * Required: No
  * Default: 0
  * Comment: The offset. Useful if you want to page through the songs in a genre.
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return albums in the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<songsByGenre>` element on success. [Example](inc/api/examples/songsByGenre_example_1.xml).

### getNowPlaying

`http://your-server/rest/getNowPlaying` Since [1.0.0](#versions)

Returns what is currently being played by all users. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<nowPlaying>` element on success. [Example](inc/api/examples/nowPlaying_example_1.xml).

### getStarred

`http://your-server/rest/getStarred` Since [1.8.0](#versions)

Returns starred songs, albums and artists.



* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return results from the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<starred>` element on success. [Example](inc/api/examples/starred_example_1.xml).

### getStarred2

`http://your-server/rest/getStarred2` Since [1.8.0](#versions)

Similar to `getStarred`, but organizes music according to ID3 tags.



* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return results from the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<starred2>` element on success. [Example](inc/api/examples/starred2_example_1.xml).

### search

`http://your-server/rest/search` Since [1.0.0](#versions)  
Deprecated since [1.4.0](#versions), use `search2` instead.

Returns a listing of files matching the given search criteria. Supports paging through the result.



* Parameter: artist
  * Required: No
  * Default: 
  * Comment: Artist to search for.
* Parameter: album
  * Required: No
  * Default: 
  * Comment: Album to searh for.
* Parameter: title
  * Required: No
  * Default: 
  * Comment: Song title to search for.
* Parameter: any
  * Required: No
  * Default: 
  * Comment: Searches all fields.
* Parameter: count
  * Required: No
  * Default: 20
  * Comment: Maximum number of results to return.
* Parameter: offset
  * Required: No
  * Default: 0
  * Comment: Search result offset. Used for paging.
* Parameter: newerThan
  * Required: No
  * Default: 
  * Comment: Only return matches that are newer than this. Given as milliseconds since 1970.


Returns a `<subsonic-response>` element with a nested `<searchResult>` element on success. [Example](inc/api/examples/searchResult_example_1.xml).

### search2

`http://your-server/rest/search2` Since [1.4.0](#versions)

Returns albums, artists and songs matching the given search criteria. Supports paging through the result.



* Parameter: query
  * Required: Yes
  * Default: 
  * Comment: Search query.
* Parameter: artistCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of artists to return.
* Parameter: artistOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for artists. Used for paging.
* Parameter: albumCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of albums to return.
* Parameter: albumOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for albums. Used for paging.
* Parameter: songCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of songs to return.
* Parameter: songOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for songs. Used for paging.
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return results from the music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<searchResult2>` element on success. [Example](inc/api/examples/searchResult2_example_1.xml).

### search3

`http://your-server/rest/search3` Since [1.8.0](#versions)

Similar to `search2`, but organizes music according to ID3 tags.



* Parameter: query
  * Required: Yes
  * Default: 
  * Comment: Search query.
* Parameter: artistCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of artists to return.
* Parameter: artistOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for artists. Used for paging.
* Parameter: albumCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of albums to return.
* Parameter: albumOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for albums. Used for paging.
* Parameter: songCount
  * Required: No
  * Default: 20
  * Comment: Maximum number of songs to return.
* Parameter: songOffset
  * Required: No
  * Default: 0
  * Comment: Search result offset for songs. Used for paging.
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) Only return results from music folder with the given ID. See getMusicFolders.


Returns a `<subsonic-response>` element with a nested `<searchResult3>` element on success. [Example](inc/api/examples/searchResult3_example_1.xml).

### getPlaylists

`http://your-server/rest/getPlaylists` Since [1.0.0](#versions)

Returns all playlists a user is allowed to play.



* Parameter: username
  * Required: no
  * Default: 
  * Comment: (Since 1.8.0) If specified, return playlists for this user rather than for the                authenticated user. The authenticated user must                have admin role if this parameter is used.            


Returns a `<subsonic-response>` element with a nested `<playlists>` element on success. [Example](inc/api/examples/playlists_example_1.xml).

### getPlaylist

`http://your-server/rest/getPlaylist` Since [1.0.0](#versions)

Returns a listing of files in a saved playlist.


|Parameter|Required|Default|Comment                                                   |
|---------|--------|-------|----------------------------------------------------------|
|id       |yes     |       |ID of the playlist to return, as obtained by getPlaylists.|


Returns a `<subsonic-response>` element with a nested `<playlist>` element on success. [Example](inc/api/examples/playlist_example_1.xml).

### createPlaylist

`http://your-server/rest/createPlaylist` Since [1.2.0](#versions)

Creates (or updates) a playlist.



* Parameter: playlistId
  * Required: Yes (if updating)
  * Default: 
  * Comment: The playlist ID.
* Parameter: name
  * Required: Yes (if creating)
  * Default: 
  * Comment: The human-readable name of the playlist.
* Parameter: songId
  * Required: No
  * Default: 
  * Comment: ID of a song in the playlist. Use one songId parameter for each song in the playlist.


Since [1.14.0](#versions) the newly created/updated playlist is returned. In earlier versions an empty `<subsonic-response>` element is returned.

### updatePlaylist

`http://your-server/rest/updatePlaylist` Since [1.8.0](#versions)

Updates a playlist. Only the owner of a playlist is allowed to update it.



* Parameter: playlistId
  * Required: Yes
  * Default: 
  * Comment: The playlist ID.
* Parameter: name
  * Required: No
  * Default: 
  * Comment: The human-readable name of the playlist.
* Parameter: comment
  * Required: No
  * Default: 
  * Comment: The playlist comment.
* Parameter: public
  * Required: No
  * Default: 
  * Comment: true if the playlist should be visible to all users, false otherwise.
* Parameter: songIdToAdd
  * Required: No
  * Default: 
  * Comment: Add this song with this ID to the playlist. Multiple parameters allowed.
* Parameter: songIndexToRemove
  * Required: No
  * Default: 
  * Comment: Remove the song at this position in the playlist. Multiple parameters allowed.


Returns an empty `<subsonic-response>` element on success.

### deletePlaylist

`http://your-server/rest/deletePlaylist` Since [1.2.0](#versions)

Deletes a saved playlist.


|Parameter|Required|Default|Comment                                                   |
|---------|--------|-------|----------------------------------------------------------|
|id       |yes     |       |ID of the playlist to delete, as obtained by getPlaylists.|


Returns an empty `<subsonic-response>` element on success.

### stream

`http://your-server/rest/stream` Since [1.0.0](#versions)

Streams a given media file.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the file to stream. Obtained by calls to getMusicDirectory.
* Parameter: maxBitRate
  * Required: No
  * Default: 
  * Comment: (Since 1.2.0) If specified, the server will attempt to limit the bitrate                to this value, in kilobits per second. If set to zero, no limit is imposed.            
* Parameter: format
  * Required: No
  * Default: 
  * Comment: (Since 1.6.0) Specifies the preferred target format (e.g., "mp3" or "flv") in                case there are multiple applicable transcodings. Starting with 1.9.0 you can use the                special value "raw" to disable transcoding.            
* Parameter: timeOffset
  * Required: No
  * Default: 
  * Comment: Only applicable to video streaming. If specified, start streaming at the given offset (in seconds) into                the video. Typically used to implement video skipping.            
* Parameter: size
  * Required: No
  * Default: 
  * Comment: (Since 1.6.0) Only applicable to video streaming. Requested video size specified                as WxH, for instance "640x480".            
* Parameter: estimateContentLength
  * Required: No
  * Default: false
  * Comment: (Since 1.8.0). If set to "true", the Content-Length HTTP header will be                set to an estimated value for transcoded or downsampled media.            
* Parameter: converted
  * Required: No
  * Default: false
  * Comment: (Since 1.14.0) Only applicable to video streaming. Subsonic can optimize videos for streaming                by converting them to MP4. If a conversion exists for the video in question, then setting this parameter to "true" will                cause the converted video to be returned instead of the original.            


Returns binary data on success, or an XML document on error (in which case the HTTP content type will start with "text/xml").

### download

`http://your-server/rest/download` Since [1.0.0](#versions)

Downloads a given media file. Similar to `stream`, but this method returns the original media data without transcoding or downsampling.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the file to download. Obtained by calls to getMusicDirectory.


Returns binary data on success, or an XML document on error (in which case the HTTP content type will start with "text/xml").

### hls

`http://your-server/rest/hls.m3u8` Since [1.8.0](#versions)

Creates an HLS ([HTTP Live Streaming](http://en.wikipedia.org/wiki/HTTP_Live_Streaming)) playlist used for streaming video or audio. HLS is a streaming protocol implemented by Apple and works by breaking the overall stream into a sequence of small HTTP-based file downloads. It's supported by iOS and newer versions of Android. This method also supports **adaptive bitrate streaming**, see the `bitRate` parameter.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the media file to stream.
* Parameter: bitRate
  * Required: No
  * Default: 
  * Comment: If specified, the server will attempt to limit the bitrate to this value, in kilobits per second.                If this parameter is specified more than once, the server will create a variant                    playlist,                suitable for adaptive bitrate streaming. The playlist will support streaming at all the specified                bitrates.                The server will automatically choose video dimensions that are suitable for the given bitrates. Since                1.9.0 you may explicitly request a certain width (480) and height (360) like so:                bitRate=1000@480x360            
* Parameter: audioTrack
  * Required: No
  * Default: 
  * Comment: The ID of the audio track to use. See getVideoInfo for how to get the list of available                audio tracks for a video.            


Returns an M3U8 playlist on success (content type "application/vnd.apple.mpegurl"), or an XML document on error (in which case the HTTP content type will start with "text/xml").

### getCaptions

`http://your-server/rest/getCaptions` Since [1.14.0](#versions)

Returns captions (subtitles) for a video. Use `getVideoInfo` to get a list of available captions.


|Parameter|Required|Default|Comment                                    |
|---------|--------|-------|-------------------------------------------|
|id       |Yes     |       |The ID of the video.                       |
|format   |No      |       |Preferred captions format ("srt" or "vtt").|


Returns the raw video captions.

### getCoverArt

`http://your-server/rest/getCoverArt` Since [1.0.0](#versions)

Returns a cover art image.


|Parameter|Required|Default|Comment                                |
|---------|--------|-------|---------------------------------------|
|id       |Yes     |       |The ID of a song, album or artist.     |
|size     |No      |       |If specified, scale image to this size.|


Returns the cover art image in binary form.

### getLyrics

`http://your-server/rest/getLyrics` Since [1.2.0](#versions)

Searches for and returns lyrics for a given song.


|Parameter|Required|Default|Comment         |
|---------|--------|-------|----------------|
|artist   |No      |       |The artist name.|
|title    |No      |       |The song title. |


Returns a `<subsonic-response>` element with a nested `<lyrics>` element on success. The `<lyrics>` element is empty if no matching lyrics was found. [Example](inc/api/examples/lyrics_example_1.xml).

### getAvatar

`http://your-server/rest/getAvatar` Since [1.8.0](#versions)

Returns the avatar (personal image) for a user.


|Parameter|Required|Default|Comment              |
|---------|--------|-------|---------------------|
|username |Yes     |       |The user in question.|


Returns the avatar image in binary form.

### star

`http://your-server/rest/star` Since [1.8.0](#versions)

Attaches a star to a song, album or artist.



* Parameter: id
  * Required: No
  * Default: 
  * Comment: The ID of the file (song) or folder (album/artist) to star. Multiple parameters allowed.
* Parameter: albumId
  * Required: No
  * Default: 
  * Comment: The ID of an album to star. Use this rather than id if the client accesses the media                collection                according to ID3                tags rather than file structure. Multiple parameters allowed.            
* Parameter: artistId
  * Required: No
  * Default: 
  * Comment: The ID of an artist to star. Use this rather than id if the client accesses the media                collection according to ID3                tags rather than file structure. Multiple parameters allowed.            


Returns an empty `<subsonic-response>` element on success.

### unstar

`http://your-server/rest/unstar` Since [1.8.0](#versions)

Removes the star from a song, album or artist.



* Parameter: id
  * Required: No
  * Default: 
  * Comment: The ID of the file (song) or folder (album/artist) to unstar. Multiple parameters allowed.
* Parameter: albumId
  * Required: No
  * Default: 
  * Comment: The ID of an album to unstar. Use this rather than id if the client accesses the media                collection according to ID3                tags rather than file structure. Multiple parameters allowed.            
* Parameter: artistId
  * Required: No
  * Default: 
  * Comment: The ID of an artist to unstar. Use this rather than id if the client accesses the media                collection according to ID3                tags rather than file structure. Multiple parameters allowed.            


Returns an empty `<subsonic-response>` element on success.

### setRating

`http://your-server/rest/setRating` Since [1.6.0](#versions)

Sets the rating for a music file.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the file (song) or folder (album/artist) to rate.
* Parameter: rating
  * Required: Yes
  * Default: 
  * Comment: The rating between 1 and 5 (inclusive), or 0 to remove the rating.


Returns an empty `<subsonic-response>` element on success.

### scrobble

`http://your-server/rest/scrobble` Since [1.5.0](#versions)

Registers the local playback of one or more media files. Typically used when playing media that is cached on the client. This operation includes the following:

*   "Scrobbles" the media files on last.fm if the user has configured his/her last.fm credentials on the Subsonic server (Settings > Personal).
*   Updates the play count and last played timestamp for the media files. (Since [1.11.0](#versions))
*   Makes the media files appear in the "Now playing" page in the web app, and appear in the list of songs returned by `getNowPlaying` (Since [1.11.0](#versions))

Since [1.8.0](#versions) you may specify multiple `id` (and optionally `time`) parameters to scrobble multiple files.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: A string which uniquely identifies the file to scrobble.
* Parameter: time
  * Required: No
  * Default: 
  * Comment: (Since 1.8.0) The time (in milliseconds since 1 Jan 1970) at which the song was                listened to.            
* Parameter: submission
  * Required: No
  * Default: True
  * Comment: Whether this is a "submission" or a "now playing" notification.


Returns an empty `<subsonic-response>` element on success.

### getShares

`http://your-server/rest/getShares` Since [1.6.0](#versions)

Returns information about shared media this user is allowed to manage. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<shares>` element on success. [Example](inc/api/examples/shares_example_1.xml).

### createShare

`http://your-server/rest/createShare` Since [1.6.0](#versions)

Creates a public URL that can be used by anyone to stream music or video from the Subsonic server. The URL is short and suitable for posting on Facebook, Twitter etc. Note: The user must be authorized to share (see Settings > Users > User is allowed to share files with anyone).



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: ID of a song, album or video to share. Use one id parameter for each entry to share.
* Parameter: description
  * Required: No
  * Default: 
  * Comment: A user-defined description that will be displayed to people visiting the shared media.
* Parameter: expires
  * Required: No
  * Default: 
  * Comment: The time at which the share expires. Given as milliseconds since 1970.


Returns a `<subsonic-response>` element with a nested `<shares>` element on success, which in turns contains a single `<share>` element for the newly created share. [Example](inc/api/examples/shares_example_1.xml).

### updateShare

`http://your-server/rest/updateShare` Since [1.6.0](#versions)

Updates the description and/or expiration date for an existing share.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: ID of the share to update.
* Parameter: description
  * Required: No
  * Default: 
  * Comment: A user-defined description that will be displayed to people visiting the shared media.
* Parameter: expires
  * Required: No
  * Default: 
  * Comment: The time at which the share expires. Given as milliseconds since 1970, or zero to remove the expiration.            


Returns an empty `<subsonic-response>` element on success.

### deleteShare

`http://your-server/rest/deleteShare` Since [1.6.0](#versions)

Deletes an existing share.


|Parameter|Required|Default|Comment                   |
|---------|--------|-------|--------------------------|
|id       |Yes     |       |ID of the share to delete.|


Returns an empty `<subsonic-response>` element on success.

### getPodcasts

`http://your-server/rest/getPodcasts` Since [1.6.0](#versions)

Returns all Podcast channels the server subscribes to, and (optionally) their episodes. This method can also be used to return details for only one channel - refer to the `id` parameter. A typical use case for this method would be to first retrieve all channels without episodes, and then retrieve all episodes for the single channel the user selects.



* Parameter: includeEpisodes
  * Required: No
  * Default: true
  * Comment: (Since 1.9.0) Whether to include Podcast episodes in the returned result.
* Parameter: id
  * Required: No
  * Default: 
  * Comment: (Since 1.9.0) If specified, only return the Podcast channel with this ID.


Returns a `<subsonic-response>` element with a nested `<podcasts>` element on success. [Example](inc/api/examples/podcasts_example_1.xml).

### getNewestPodcasts

`http://your-server/rest/getNewestPodcasts` Since [1.13.0](#versions)

Returns the most recently published Podcast episodes.


|Parameter|Required|Default|Comment                                  |
|---------|--------|-------|-----------------------------------------|
|count    |No      |20     |The maximum number of episodes to return.|


Returns a `<subsonic-response>` element with a nested `<newestPodcasts>` element on success. [Example](inc/api/examples/newest_podcasts_example_1.xml).

### refreshPodcasts

`http://your-server/rest/refreshPodcasts` Since [1.9.0](#versions)

Requests the server to check for new Podcast episodes. Note: The user must be authorized for Podcast administration (see Settings > Users > User is allowed to administrate Podcasts).

Returns an empty `<subsonic-response>` element on success.

### createPodcastChannel

`http://your-server/rest/createPodcastChannel` Since [1.9.0](#versions)

Adds a new Podcast channel. Note: The user must be authorized for Podcast administration (see Settings > Users > User is allowed to administrate Podcasts).


|Parameter|Required|Default|Comment                       |
|---------|--------|-------|------------------------------|
|url      |Yes     |       |The URL of the Podcast to add.|


Returns an empty `<subsonic-response>` element on success.

### deletePodcastChannel

`http://your-server/rest/deletePodcastChannel` Since [1.9.0](#versions)

Deletes a Podcast channel. Note: The user must be authorized for Podcast administration (see Settings > Users > User is allowed to administrate Podcasts).


|Parameter|Required|Default|Comment                                 |
|---------|--------|-------|----------------------------------------|
|id       |Yes     |       |The ID of the Podcast channel to delete.|


Returns an empty `<subsonic-response>` element on success.

### deletePodcastEpisode

`http://your-server/rest/deletePodcastEpisode` Since [1.9.0](#versions)

Deletes a Podcast episode. Note: The user must be authorized for Podcast administration (see Settings > Users > User is allowed to administrate Podcasts).


|Parameter|Required|Default|Comment                                 |
|---------|--------|-------|----------------------------------------|
|id       |Yes     |       |The ID of the Podcast episode to delete.|


Returns an empty `<subsonic-response>` element on success.

### downloadPodcastEpisode

`http://your-server/rest/downloadPodcastEpisode` Since [1.9.0](#versions)

Request the server to start downloading a given Podcast episode. Note: The user must be authorized for Podcast administration (see Settings > Users > User is allowed to administrate Podcasts).


|Parameter|Required|Default|Comment                                   |
|---------|--------|-------|------------------------------------------|
|id       |Yes     |       |The ID of the Podcast episode to download.|


Returns an empty `<subsonic-response>` element on success.

### jukeboxControl

`http://your-server/rest/jukeboxControl` Since [1.2.0](#versions)

Controls the jukebox, i.e., playback directly on the server's audio hardware. Note: The user must be authorized to control the jukebox (see Settings > Users > User is allowed to play files in jukebox mode).



* Parameter: action
  * Required: Yes
  * Default: 
  * Comment: The operation to perform. Must be one of: get, status (since 1.7.0),                set (since 1.7.0),                start, stop, skip, add, clear,                remove, shuffle, setGain            
* Parameter: index
  * Required: No
  * Default: 
  * Comment: Used by skip and remove. Zero-based index of the song to skip to or remove.            
* Parameter: offset
  * Required: No
  * Default: 
  * Comment: (Since 1.7.0) Used by skip. Start playing this many seconds into                the                track.            
* Parameter: id
  * Required: No
  * Default: 
  * Comment: Used by add and set. ID of song to add to the jukebox playlist. Use multiple                id parameters                to add many songs in the same request. (set is similar to a clear followed by                a                add, but                will not change the currently playing track.)            
* Parameter: gain
  * Required: No
  * Default: 
  * Comment: Used by setGain to control the playback volume. A float value between 0.0 and 1.0.


Returns a `<jukeboxStatus>` element on success, unless the `get` action is used, in which case a nested `<jukeboxPlaylist>` element is returned. [Example 1](inc/api/examples/jukeboxStatus_example_1.xml). [Example 2](inc/api/examples/jukeboxPlaylist_example_1.xml).

### getInternetRadioStations

`http://your-server/rest/getInternetRadioStations` Since [1.9.0](#versions)

Returns all internet radio stations. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<internetRadioStations>` element on success. [Example](inc/api/examples/internetRadioStations_example_1.xml).

### createInternetRadioStation

`http://your-server/rest/createInternetRadioStation` Since [1.16.0](#versions)

Adds a new internet radio station. Only users with admin privileges are allowed to call this method.


|Parameter  |Required|Default|Comment                               |
|-----------|--------|-------|--------------------------------------|
|streamUrl  |Yes     |       |The stream URL for the station.       |
|name       |Yes     |       |The user-defined name for the station.|
|homepageUrl|No      |       |The home page URL for the station.    |


Returns an empty `<subsonic-response>` element on success.

### updateInternetRadioStation

`http://your-server/rest/updateInternetRadioStation` Since [1.16.0](#versions)

Updates an existing internet radio station. Only users with admin privileges are allowed to call this method.


|Parameter  |Required|Default|Comment                               |
|-----------|--------|-------|--------------------------------------|
|id         |Yes     |       |The ID for the station.               |
|streamUrl  |Yes     |       |The stream URL for the station.       |
|name       |Yes     |       |The user-defined name for the station.|
|homepageUrl|No      |       |The home page URL for the station.    |


Returns an empty `<subsonic-response>` element on success.

### deleteInternetRadioStation

`http://your-server/rest/deleteInternetRadioStation` Since [1.16.0](#versions)

Deletes an existing internet radio station. Only users with admin privileges are allowed to call this method.


|Parameter|Required|Default|Comment                |
|---------|--------|-------|-----------------------|
|id       |Yes     |       |The ID for the station.|


Returns an empty `<subsonic-response>` element on success.

### getChatMessages

`http://your-server/rest/getChatMessages` Since [1.2.0](#versions)

Returns the current visible (non-expired) chat messages.


|Parameter|Required|Default|Comment                                                                |
|---------|--------|-------|-----------------------------------------------------------------------|
|since    |No      |       |Only return messages newer than this time (in millis since Jan 1 1970).|


Returns a `<subsonic-response>` element with a nested `<chatMessages>` element on success. [Example](inc/api/examples/chatMessages_example_1.xml).

### addChatMessage

`http://your-server/rest/addChatMessage` Since [1.2.0](#versions)

Adds a message to the chat log.


|Parameter|Required|Default|Comment          |
|---------|--------|-------|-----------------|
|message  |Yes     |       |The chat message.|


Returns an empty `<subsonic-response>` element on success.

### getUser

`http://your-server/rest/getUser` Since [1.3.0](#versions)

Get details about a given user, including which authorization roles and folder access it has. Can be used to enable/disable certain features in the client, such as jukebox control.



* Parameter: username
  * Required: Yes
  * Default: 
  * Comment: The name of the user to retrieve. You can only retrieve your own user unless you have admin                privileges.            


Returns a `<subsonic-response>` element with a nested `<user>` element on success. [Example](inc/api/examples/user_example_1.xml).

### getUsers

`http://your-server/rest/getUsers` Since [1.8.0](#versions)

Get details about all users, including which authorization roles and folder access they have. Only users with admin privileges are allowed to call this method.

Returns a `<subsonic-response>` element with a nested `<users>` element on success. [Example](inc/api/examples/users_example_1.xml).

### createUser

`http://your-server/rest/createUser` Since [1.1.0](#versions)

Creates a new Subsonic user, using the following parameters:



* Parameter: username
  * Required: Yes
  * Default: 
  * Comment: The name of the new user.
* Parameter: password
  * Required: Yes
  * Default: 
  * Comment: The password of the new user, either in clear text of hex-encoded (see above).
* Parameter: email
  * Required: Yes
  * Default: 
  * Comment: The email address of the new user.
* Parameter: ldapAuthenticated
  * Required: No
  * Default: false
  * Comment: Whether the user is authenicated in LDAP.
* Parameter: adminRole
  * Required: No
  * Default: false
  * Comment: Whether the user is administrator.
* Parameter: settingsRole
  * Required: No
  * Default: true
  * Comment: Whether the user is allowed to change personal settings and password.
* Parameter: streamRole
  * Required: No
  * Default: true
  * Comment: Whether the user is allowed to play files.
* Parameter: jukeboxRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to play files in jukebox mode.
* Parameter: downloadRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to download files.
* Parameter: uploadRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to upload files.
* Parameter: playlistRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to create and delete playlists. Since 1.8.0, changing this role has no                effect.            
* Parameter: coverArtRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to change cover art and tags.
* Parameter: commentRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to create and edit comments and ratings.
* Parameter: podcastRole
  * Required: No
  * Default: false
  * Comment: Whether the user is allowed to administrate Podcasts.
* Parameter: shareRole
  * Required: No
  * Default: false
  * Comment: (Since 1.8.0) Whether the user is allowed to share files with anyone.
* Parameter: videoConversionRole
  * Required: No
  * Default: false
  * Comment: (Since 1.15.0) Whether the user is allowed to start video conversions.
* Parameter: musicFolderId
  * Required: No
  * Default: All folders
  * Comment: (Since 1.12.0) IDs of the music folders the user is allowed access to. Include the parameter once for each folder.


Returns an empty `<subsonic-response>` element on success.

### updateUser

`http://your-server/rest/updateUser` Since [1.10.1](#versions)

Modifies an existing Subsonic user, using the following parameters:



* Parameter: username
  * Required: Yes
  * Default: 
  * Comment: The name of the user.
* Parameter: password
  * Required: No
  * Default: 
  * Comment: The password of the user, either in clear text of hex-encoded (see above).
* Parameter: email
  * Required: No
  * Default: 
  * Comment: The email address of the user.
* Parameter: ldapAuthenticated
  * Required: No
  * Default: 
  * Comment: Whether the user is authenicated in LDAP.
* Parameter: adminRole
  * Required: No
  * Default: 
  * Comment: Whether the user is administrator.
* Parameter: settingsRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to change personal settings and password.
* Parameter: streamRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to play files.
* Parameter: jukeboxRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to play files in jukebox mode.
* Parameter: downloadRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to download files.
* Parameter: uploadRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to upload files.
* Parameter: coverArtRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to change cover art and tags.
* Parameter: commentRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to create and edit comments and ratings.
* Parameter: podcastRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to administrate Podcasts.
* Parameter: shareRole
  * Required: No
  * Default: 
  * Comment: Whether the user is allowed to share files with anyone.
* Parameter: videoConversionRole
  * Required: No
  * Default: false
  * Comment: (Since 1.15.0) Whether the user is allowed to start video conversions.
* Parameter: musicFolderId
  * Required: No
  * Default: 
  * Comment: (Since 1.12.0) IDs of the music folders the user is allowed access to. Include the parameter once for each folder.
* Parameter: maxBitRate
  * Required: No
  * Default: 
  * Comment: (Since 1.13.0) The maximum bit rate (in Kbps) for the user. Audio streams of higher bit rates are                automatically downsampled to this bit rate. Legal values: 0 (no limit), 32, 40, 48, 56, 64, 80, 96, 112, 128,                160, 192, 224, 256, 320.            


Returns an empty `<subsonic-response>` element on success.

### deleteUser

`http://your-server/rest/deleteUser` Since [1.3.0](#versions)

Deletes an existing Subsonic user, using the following parameters:


|Parameter|Required|Default|Comment                        |
|---------|--------|-------|-------------------------------|
|username |Yes     |       |The name of the user to delete.|


Returns an empty `<subsonic-response>` element on success.

### changePassword

`http://your-server/rest/changePassword` Since [1.1.0](#versions)

Changes the password of an existing Subsonic user, using the following parameters. You can only change your own password unless you have admin privileges.



* Parameter: username
  * Required: Yes
  * Default: 
  * Comment: The name of the user which should change its password.
* Parameter: password
  * Required: Yes
  * Default: 
  * Comment: The new password of the new user, either in clear text of hex-encoded (see above).


Returns an empty `<subsonic-response>` element on success.

### getBookmarks

`http://your-server/rest/getBookmarks` Since [1.9.0](#versions)

Returns all bookmarks for this user. A bookmark is a position within a certain media file.

Returns a `<subsonic-response>` element with a nested `<bookmarks>` element on success. [Example](inc/api/examples/bookmarks_example_1.xml).

### createBookmark

`http://your-server/rest/createBookmark` Since [1.9.0](#versions)

Creates or updates a bookmark (a position within a media file). Bookmarks are personal and not visible to other users.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: ID of the media file to bookmark. If a bookmark already exists for this file it will be overwritten.            
* Parameter: position
  * Required: Yes
  * Default: 
  * Comment: The position (in milliseconds) within the media file.
* Parameter: comment
  * Required: No
  * Default: 
  * Comment: A user-defined comment.


Returns an empty `<subsonic-response>` element on success.

### deleteBookmark

`http://your-server/rest/deleteBookmark` Since [1.9.0](#versions)

Deletes the bookmark for a given file.



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: ID of the media file for which to delete the bookmark. Other users' bookmarks are not affected.


Returns an empty `<subsonic-response>` element on success.

### getPlayQueue

`http://your-server/rest/getPlayQueue` Since [1.12.0](#versions)

Returns the state of the play queue for this user (as set by `savePlayQueue`). This includes the tracks in the play queue, the currently playing track, and the position within this track. Typically used to allow a user to move between different clients/apps while retaining the same play queue (for instance when listening to an audio book).

Returns a `<subsonic-response>` element with a nested `<playQueue>` element on success, or an empty `<subsonic-response>` if no play queue has been saved. [Example](inc/api/examples/playQueue_example_1.xml).

### savePlayQueue

`http://your-server/rest/savePlayQueue` Since [1.12.0](#versions)

Saves the state of the play queue for this user. This includes the tracks in the play queue, the currently playing track, and the position within this track. Typically used to allow a user to move between different clients/apps while retaining the same play queue (for instance when listening to an audio book).



* Parameter: id
  * Required: Yes
  * Default: 
  * Comment: ID of a song in the play queue. Use one id parameter for each song in the play queue.
* Parameter: current
  * Required: No
  * Default: 
  * Comment: The ID of the current playing song.
* Parameter: position
  * Required: No
  * Default: 
  * Comment: The position in milliseconds within the currently playing song.


Returns an empty `<subsonic-response>` element on success.

### getScanStatus

`http://your-server/rest/getScanStatus` Since [1.15.0](#versions)

Returns the current status for media library scanning. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<scanStatus>` element on success. [Example](inc/api/examples/scanStatus_example_1.xml).

### startScan

`http://your-server/rest/startScan` Since [1.15.0](#versions)

Initiates a rescan of the media libraries. Takes no extra parameters.

Returns a `<subsonic-response>` element with a nested `<scanStatus>` element on success. [Example](inc/api/examples/scanStatus_example_1.xml).