{-# LANGUAGE OverloadedStrings #-}
module Main where

import Data.Aeson (Value(..), decode, encode, object, (.=))
import qualified Data.Aeson as AE
import qualified Data.Aeson.Key as K
import qualified Data.Aeson.KeyMap as KM
import qualified Data.ByteString.Lazy as BL
import Data.List (sort, sortOn)
import Data.Maybe (mapMaybe)
import qualified Data.Map.Strict as M
import qualified Data.Set as S
import System.Directory (createDirectoryIfMissing, listDirectory)
import System.Environment (lookupEnv)
import System.FilePath ((</>))
import Data.Text (pack, unpack)
import qualified Data.Vector as V

envOr :: String -> String -> IO String
envOr k d = maybe d id <$> lookupEnv k

load :: FilePath -> IO Value
load p = BL.readFile p >>= \b -> case decode b of
  Nothing -> fail ("decode failed: " ++ p)
  Just v -> pure v

asInt :: Value -> Int
asInt (Number n) = truncate n
asInt _ = 0

asStr :: Value -> String
asStr (String s) = unpack s
asStr _ = ""

kv :: Value -> [(String, Value)]
kv (Object o) = [(unpack (K.toText k), v) | (k, v) <- KM.toList o]
kv _ = []

arr :: Value -> [Value]
arr (Array a) = V.toList a
arr _ = []

main :: IO ()
main = do
  dataDir <- envOr "QUOTA_DATA_DIR" "/app/quota_lab"
  auditDir <- envOr "QUOTA_AUDIT_DIR" "/app/audit"
  createDirectoryIfMissing True auditDir
  policy <- load (dataDir </> "policy.json")
  events <- load (dataDir </> "events.json")
  let pol = M.fromList (kv policy)
      day = asInt (M.findWithDefault (Number 0) "audit_day" pol)
      order = map asStr (maybe [] arr (M.lookup "tier_order" pol))
      caps0 = M.fromList [(k, asInt v) | (k, v) <- kv (maybe (Object KM.empty) id (M.lookup "tier_caps" pol))]
      ev = M.fromList (kv events)
      derates = case M.lookup "tier_derates" ev of Just v -> arr v; Nothing -> []
      caps = foldl (applyDerate day) caps0 derates
      freezes = case M.lookup "item_freezes" ev of Just v -> arr v; Nothing -> []
      frozen = S.fromList $ mapMaybe frozenId freezes
        where
          frozenId fr =
            let f = M.fromList (kv fr)
                s = asInt (M.findWithDefault (Number 0) "start_day" f)
                e = asInt (M.findWithDefault (Number 0) "end_day" f)
            in if s <= day && day <= e then Just (asStr (M.findWithDefault (String "") "item_id" f)) else Nothing
  files <- sort . filter (".json" `isSuffixOf`) <$> listDirectory (dataDir </> "items")
  items <- mapM (\f -> load (dataDir </> "items" </> f)) files
  let rank t = case lookup t (zip order [0..]) of Just i -> i; Nothing -> length order
      sorted = sortOn (\it -> let f = M.fromList (kv it); tier = asStr (M.findWithDefault (String "") "tier" f); iid = asStr (M.findWithDefault (String "") "item_id" f) in (rank tier, tier, iid)) items
      step (acc, sc, rem) it =
        let f = M.fromList (kv it)
            iid = asStr (M.findWithDefault (String "") "item_id" f)
            tier = asStr (M.findWithDefault (String "") "tier" f)
            demand = asInt (M.findWithDefault (Number 0) "demand" f)
        in if S.member iid frozen
          then
            let row =
                  object
                    [ "item_id" .= pack iid,
                      "tier" .= pack tier,
                      "status" .= pack ("frozen" :: String),
                      "demand" .= demand,
                      "allocated" .= (0 :: Int)
                    ]
            in (acc ++ [row], M.adjust (+1) "frozen" sc, rem)
          else
            let left = M.findWithDefault 0 tier rem
                alloc = min demand left
                rem2 = M.insert tier (left - alloc) rem
                st = if alloc == demand then "ok" else "shortfall" :: String
                row =
                  object
                    [ "item_id" .= pack iid,
                      "tier" .= pack tier,
                      "status" .= pack st,
                      "demand" .= demand,
                      "allocated" .= alloc
                    ]
            in (acc ++ [row], M.adjust (+1) st sc, rem2)
      (rows, sc, _) = foldl step ([], M.fromList [("frozen",0),("ok",0),("shortfall",0)] :: M.Map String Int, caps) sorted
      touched = sort [asStr (M.findWithDefault (String "") "tier" (M.fromList (kv r))) | r <- rows, asInt (M.findWithDefault (Number 0) "allocated" (M.fromList (kv r))) > 0]
      summary =
        object
          [ "audit_day" .= day,
            "items_processed" .= length items,
            "frozen_items" .= M.findWithDefault 0 "frozen" sc,
            "status_counts"
              .= object
                [ "frozen" .= M.findWithDefault 0 "frozen" sc,
                  "ok" .= M.findWithDefault 0 "ok" sc,
                  "shortfall" .= M.findWithDefault 0 "shortfall" sc
                ],
            "tiers_touched" .= map (\t -> String (pack t)) touched
          ]
  BL.writeFile (auditDir </> "allocations.json") (encode (object ["items" .= rows]) <> "\n")
  BL.writeFile (auditDir </> "summary.json") (encode summary <> "\n")
  where
    applyDerate auditDay m d =
      let f = M.fromList (kv d)
          s = asInt (M.findWithDefault (Number 0) "start_day" f)
          e = asInt (M.findWithDefault (Number 0) "end_day" f)
          t = asStr (M.findWithDefault (String "") "tier" f)
          bp = asInt (M.findWithDefault (Number 10000) "factor_bp" f)
      in if s <= auditDay && auditDay <= e then M.adjust (\c -> c * bp `div` 10000) t m else m

isSuffixOf :: String -> String -> Bool
isSuffixOf suf str = drop (length str - length suf) str == suf
